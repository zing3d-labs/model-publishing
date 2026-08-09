#!/usr/bin/env python3
"""Shared config-loading helpers for multi-profile models.

A model with more than one MakerWorld print profile (e.g. grid_basket's
small/medium/large sizes, opengrid_beam's Full/Lite thickness) is laid out as:

    model_pages/<model>/model.yaml           -- model-level: project identity,
                                                 source file, templates, and
                                                 the cross-profile `profiles`
                                                 list used in generated copy
    model_pages/<model>/<profile>/build_config.yaml
                                              -- profile-level: variants,
                                                 images, build settings,
                                                 makerworld_profile_id

A single-profile model (e.g. opengrid_facade) has no model.yaml and keeps
everything in one flat model_pages/<model>/build_config.yaml, unchanged.

Orthogonally, a config declares where its geometry comes from -- exactly one of:

    source:                       -- compiled from SCAD by scad_builder.py
      input_file: "...scad"

    prebuilt:                     -- the .3mf already exists and is committed
      package: "package/foo.3mf"     alongside the config; there is no build

A prebuilt model is for geometry that was never authored in OpenSCAD (a CAD
export, a hand-assembled plate). Its package is committed under model_pages/
rather than produced into dist/, which is gitignored and would be wiped by the
next build of any model.
"""

from pathlib import Path

import yaml

PREBUILT_SUFFIX = '.3mf'


def deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base, returning a new dict.
    override's values win on any key collision; nested dicts are merged
    key-by-key rather than replaced wholesale."""
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_merged_config(config_path: Path) -> tuple[dict, Path | None]:
    """Load a build_config.yaml, merging in a sibling model.yaml one directory
    up if present. Returns (config, model_dir) -- model_dir is the directory
    containing model.yaml (for locating model-level sections/ overrides), or
    None for a single-profile model with no model.yaml."""
    with open(config_path) as f:
        profile_config = yaml.safe_load(f)

    model_yaml_path = config_path.parent.parent / 'model.yaml'
    if not model_yaml_path.exists():
        validate_geometry_source(profile_config, config_path)
        return profile_config, None

    with open(model_yaml_path) as f:
        model_config = yaml.safe_load(f)

    merged = deep_merge(model_config, profile_config)
    validate_geometry_source(merged, config_path)
    return merged, model_yaml_path.parent


def validate_geometry_source(config: dict, config_path: Path) -> None:
    """A config must say where its geometry comes from, and say it once."""
    has_source = 'source' in config
    has_prebuilt = 'prebuilt' in config
    if has_source and has_prebuilt:
        raise ValueError(
            f"{config_path} declares both 'source' and 'prebuilt'. A model is either "
            "compiled from SCAD (source) or ships a committed package (prebuilt), not both."
        )
    if not has_source and not has_prebuilt:
        raise ValueError(
            f"{config_path} declares neither 'source' nor 'prebuilt'. Add source.input_file "
            "for a SCAD model, or prebuilt.package for a model whose .3mf already exists."
        )


def is_prebuilt(config: dict) -> bool:
    """True when this config ships a committed package instead of building one."""
    return 'prebuilt' in config


def prebuilt_package_path(config: dict, config_path: Path) -> Path:
    """Resolve and validate a prebuilt model's committed .3mf.

    prebuilt.package is relative to the config's OWN directory -- for a
    multi-profile model that is the profile subdirectory, one level below the
    model.yaml, same as every other path in a merged config. The package must
    live in a subdirectory of that directory rather than loose beside the
    config, so a model's committed binary sits in one obvious place next to
    whatever else came with it (CAD export, source STLs)."""
    package = config['prebuilt'].get('package')
    if not package:
        raise ValueError(f"{config_path} has a 'prebuilt' block with no 'package' path")

    config_dir = config_path.parent.resolve()
    package_path = (config_dir / package).resolve()

    try:
        relative = package_path.relative_to(config_dir)
    except ValueError:
        raise ValueError(
            f"{config_path}: prebuilt.package '{package}' resolves outside {config_dir}. "
            "It must point inside a subdirectory of the config's own directory."
        )
    if len(relative.parts) < 2:
        raise ValueError(
            f"{config_path}: prebuilt.package '{package}' sits loose beside the config. "
            f"Put it in a subdirectory instead, e.g. 'package/{relative.name}'."
        )
    if package_path.suffix.lower() != PREBUILT_SUFFIX:
        raise ValueError(
            f"{config_path}: prebuilt.package '{package}' must be a {PREBUILT_SUFFIX} file"
        )
    if not package_path.exists():
        raise ValueError(
            f"{config_path}: prebuilt.package '{package}' not found at {package_path}. "
            "The package is committed under model_pages/ -- nothing builds it."
        )
    return package_path


def project_slug(config_path: Path, root_dir: Path) -> str:
    """A filesystem-safe, unique identifier for a model_pages config, used to
    name its dist/ output directory. Derived from the config's own location
    under model_pages/ (not project.name, which is shared identically across
    every profile of the same model and would collide)."""
    model_pages_root = root_dir / 'model_pages'
    rel = config_path.parent.resolve().relative_to(model_pages_root.resolve())
    return '_'.join(rel.parts).lower().replace(' ', '_').replace('-', '_')
