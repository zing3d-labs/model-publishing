# model-publishing

Build pipeline for publishing OpenSCAD models to MakerWorld and Printables.

Uses [openscad-models](https://github.com/zing3d-labs/openscad-models) as a git submodule for source files, and [openscad-toolkit](https://github.com/zing3d-labs/openscad-toolkit) for compilation.

## Setup

```bash
git clone --recurse-submodules https://github.com/zing3d-labs/model-publishing.git
```

## Usage

```bash
python scripts/scad_builder.py model_pages/<model>/build_config.yaml
```

Add `-d` to generate descriptions only, `-i` for images only.
