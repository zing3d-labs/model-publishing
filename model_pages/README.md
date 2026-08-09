# model_pages/

Build configurations for each publishable model. Each subdirectory contains a `build_config.yaml` that defines:

- Project metadata (name, description, license)
- Where the geometry comes from — either `source:` (a SCAD file to compile) or
  `prebuilt:` (a committed `.3mf`), exactly one of the two
- Variant definitions (parameter combinations) — SCAD models only
- Image rendering specs (camera angles, resolution)
- Template sections for marketplace descriptions

## Usage

```bash
./scripts/scad_builder.py model_pages/<model>/build_config.yaml
```

## Models

- `opengrid_beam/` - Parametric beam in Full/Lite thickness, 2-12 units
- `dual_sided_snap/` - All 8 combinations of Lite/Standard/Directional
- `grid_basket/` - Multiple basket sizes (2x2x1 through 4x4x3)

## Prebuilt models

A model that wasn't authored in OpenSCAD ships its `.3mf` instead of building one:

```yaml
prebuilt:
  package: "package/my_model.3mf"   # relative to this config's dir, in a subdirectory
```

The package is committed here rather than produced into `dist/`, and is uploaded
straight from this directory. Building such a model generates descriptions only.
See `_test_fixture_prebuilt/` for the layout.
