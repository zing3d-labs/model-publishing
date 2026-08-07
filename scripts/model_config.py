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
"""

from pathlib import Path

import yaml


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
        return profile_config, None

    with open(model_yaml_path) as f:
        model_config = yaml.safe_load(f)

    return deep_merge(model_config, profile_config), model_yaml_path.parent


def project_slug(config_path: Path, root_dir: Path) -> str:
    """A filesystem-safe, unique identifier for a model_pages config, used to
    name its dist/ output directory. Derived from the config's own location
    under model_pages/ (not project.name, which is shared identically across
    every profile of the same model and would collide)."""
    model_pages_root = root_dir / 'model_pages'
    rel = config_path.parent.resolve().relative_to(model_pages_root.resolve())
    return '_'.join(rel.parts).lower().replace(' ', '_').replace('-', '_')
