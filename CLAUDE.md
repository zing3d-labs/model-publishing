# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is the publishing pipeline for OpenSCAD models. It compiles SCAD source files, generates STL/3MF outputs, renders images, and produces formatted descriptions for MakerWorld and Printables.

OpenSCAD source files live in the `models/` submodule ([zing3d-labs/openscad-models](https://github.com/zing3d-labs/openscad-models)).

## Key Architecture

### Directory Structure
- `models/` - Git submodule: OpenSCAD source files (openscad-models repo)
- `model_pages/` - Build configs for each publishable model. Two layouts, both supported:
  - **Single-profile** (one MakerWorld print profile) — everything in one flat config:
    - `opengrid_facade/build_config.yaml`
    - `opengrid_dual_sided_snap/build_config.yaml`
  - **Multi-profile** (several print profiles on the same MakerWorld model) — a model-level
    `model.yaml` plus one subdirectory per profile:
    - `grid_basket/model.yaml` + `grid_basket/{small,medium,large}/build_config.yaml`
    - `opengrid_beam/model.yaml` + `opengrid_beam/{full,lite}/build_config.yaml`

  Orthogonally, a config declares where its geometry comes from — exactly one of `source:`
  (compiled from SCAD) or `prebuilt:` (a committed `.3mf`, see below). Either layout can use
  either one.
- `scripts/` - Python build automation:
  - `scad_builder.py` - Main build orchestrator
  - `model_config.py` - Config loading shared by the build and publish scripts
  - `stls_to_3mf.py` - 3MF packer
  - `copy_description.py` - macOS clipboard helper for MakerWorld
  - `makerworld_update.py` - Publish/update print profiles on MakerWorld (Playwright)
  - `makerworld_comments.py` - Read and reply to MakerWorld comments (Playwright)
- `templates/` - Jinja2 templates for description generation
- `dist/` - Build outputs (gitignored)

### Dependencies
- **openscad-toolkit**: SCAD compiler (`uvx --from git+https://github.com/zing3d-labs/openscad-toolkit`)
- **Python 3**: For build scripts
- **OpenSCAD**: For STL/image rendering

## Common Development Tasks

### Building a Model
```bash
# single-profile model
python scripts/scad_builder.py model_pages/opengrid_facade/build_config.yaml

# multi-profile model — always point at a profile's config, never at model.yaml
python scripts/scad_builder.py model_pages/grid_basket/small/build_config.yaml
```
- `-d` — descriptions only
- `-i` — images only

Each profile builds to its own `dist/` directory (`grid_basket_small`, `grid_basket_medium`, …)
rather than one per model, since every profile of a model shares the same `project.name`.

### Copying Description to Clipboard (MakerWorld)
```bash
python scripts/copy_description.py model_pages/<model>/build_config.yaml makerworld
```

## Build System Notes
- `scripts/scad_builder.py` orchestrates: compile → generate variants (STL/3MF) → render images → template descriptions
- Build configs in `model_pages/*/build_config.yaml` (single-profile) or
  `model_pages/*/<profile>/build_config.yaml` (multi-profile)
- `scripts/model_config.py` merges a multi-profile model's `model.yaml` into each profile's
  `build_config.yaml`, profile values winning on collision. A model with no `model.yaml` loads
  flat and unchanged — **do not migrate single-profile models to the subdirectory layout**
- Paths inside a `model.yaml` resolve from a *profile* subdirectory, one level deeper than the
  file itself
- `model.yaml`'s `profiles:` list is what lets generated copy describe a model's other profiles

### Prebuilt models (non-SCAD)
- A model whose `.3mf` already exists (CAD export, hand-assembled plate) declares a `prebuilt:`
  block **instead of** `source:`. The two are mutually exclusive; one is required
  ```yaml
  prebuilt:
    package: "package/my_model.3mf"   # relative to THIS config's dir; must be in a subdirectory
  ```
- The package is **committed under `model_pages/`** and used from there. Never copy it into
  `dist/` — that's gitignored and `clean_before_build` wipes it
- Building a prebuilt model generates descriptions only; `variants:` isn't required, and
  `-i/--images-only` is an error (there's no source to render — use real photos)
- `makerworld_update.py` uploads the committed package directly; `--scad` is refused
- See `model_pages/_test_fixture_prebuilt/` for the layout and
  `docs/makerworld_publish_notes.md` for the full rules
- Templates use Jinja2, section resolution: model-specific → collection → site-specific → shared
- Collection templates live in `templates/sections/collections/{collection}/`
- All openGrid models must have `collection: "opengrid"` in their build config `project:` block
- **Never add a `related_models` section to any model unless the user explicitly specifies which models to link**
- Canonical sections (makerworld): model_description, intro, print_settings, downloads, assembly, collection, support_project, related_models
- Canonical sections (printables): model_description, intro, print_settings, downloads, assembly, attribution, collection, support_project, related_models

## Code Conventions

### Python Scripts
- All Python scripts are executable with proper shebang lines
- Use argparse for command-line interfaces
- Handle file paths as absolute paths internally for reliability
