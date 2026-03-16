# model_pages/

Build configurations for each publishable model. Each subdirectory contains a `build_config.yaml` that defines:

- Project metadata (name, description, license)
- Source SCAD file location
- Variant definitions (parameter combinations)
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
