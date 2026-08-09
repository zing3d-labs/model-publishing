# OpenSCAD Build System

Automated build system for OpenSCAD projects that generates variants, renders images, and creates site-specific descriptions for MakerWorld, Printables, and other platforms.

## Features

- ✅ **SCAD Compilation**: Inline dependencies using `compile_scad.py`
- ✅ **Multi-Variant Generation**: Create STL/3MF files with different parameters
- ✅ **Automated Rendering**: Generate images from multiple angles
- ✅ **Modular Templates**: Site-specific descriptions using shared and custom sections
- 🚧 **File Watching**: Auto-rebuild on changes (coming soon)

## Quick Start

### 1. Install Dependencies

```bash
pip install pyyaml jinja2
```

Make sure `openscad` is installed and in your PATH:
```bash
openscad --version
```

### 2. Create Configuration File

Copy the example configuration:
```bash
cp build_config.example.yaml model_pages/my_project/build_config.yaml
```

Edit `build_config.yaml` to match your project.

### 3. Run Build

```bash
./scripts/scad_builder.py model_pages/my_project/build_config.yaml
```

## Configuration Format

### Basic Structure

```yaml
project:
  name: "My Awesome Model"
  description: "A parametric design for..."

source:
  input_file: "../../scad_code/kits/my_model/my_model.scad"
  libraries:
    - "BOSL2/"

variants:
  small:
    name: "Small Version"
    parameters:
      width: 50
      height: 30
    outputs:
      - format: "stl"
      - format: "3mf"
```

### Prebuilt models

A model whose `.3mf` already exists (a CAD export, a hand-assembled plate) replaces
`source:` with `prebuilt:`. Exactly one of the two is required:

```yaml
prebuilt:
  package: "package/my_model.3mf"   # relative to this config's dir, in a subdirectory
```

The package is committed next to the config rather than produced into `dist/`.
Building such a model generates descriptions only — there's nothing to compile,
no variants to export and nothing to render — so `variants:` is not required and
`--images-only` is an error. See `docs/makerworld_publish_notes.md`.

### Variants

Define different parameter combinations:

```yaml
variants:
  variant_name:
    name: "Human Readable Name"
    description: "Description for this variant"
    parameters:
      param1: value1
      param2: value2
      boolParam: true
    outputs:
      - format: "stl"
        filename: "custom_name.stl"
      - format: "3mf"
```

### Images

Generate rendered images:

```yaml
images:
  defaults:
    resolution: [1920, 1080]
    background: "white"
    colorscheme: "Nature"

  views:
    - variant: "small"
      shots:
        - name: "hero"
          camera:
            position: [100, -100, 80]
            look_at: [0, 0, 0]
          filename: "hero_shot.png"
```

Camera format: `position` is [x, y, z] camera location, `look_at` is [x, y, z] target point.

### Modular Templates

The template system uses a modular approach where you compose descriptions from reusable sections:

```yaml
templates:
  base_template: "templates/base_template.md"

  sites:
    makerworld:
      output_file: "dist/descriptions/makerworld.txt"
      sections:
        intro: "sections/shared/intro.md"
        variants: "sections/shared/variants.md"
        print_settings: "sections/shared/print_settings.md"
        downloads: "sections/makerworld/downloads.md"
```

## Template System

### Directory Structure

```
templates/
├── base_template.md          # Main template with section placeholders
└── sections/
    ├── shared/               # Sections used across all sites
    │   ├── intro.md
    │   ├── variants.md
    │   ├── print_settings.md
    │   └── assembly.md
    ├── makerworld/           # MakerWorld-specific sections
    │   ├── downloads.md
    │   ├── print_profile.md
    │   └── support_project.md
    └── printables/           # Printables-specific sections
        ├── downloads.md
        ├── attribution.md
        └── support_project.md
```

### Base Template

The base template (`templates/base_template.md`) uses placeholders for sections:

```markdown
# {{project.name}}

{{{sections.intro}}}

{{{sections.variants}}}

{{{sections.print_settings}}}
```

### Section Templates

Sections are Jinja2 templates with access to project data:

```markdown
## Available Variants

{% for variant in variants %}
### {{variant.name}}
{{variant.description}}
{% endfor %}
```

Available template variables:
- `project.name`
- `project.description`
- `project.version`
- `project.author`
- `variants` (dictionary of all variants)

## Output Structure

Every build writes under `dist/<slug>/`, where the slug comes from the config's own location
under `model_pages/` (`model_config.project_slug()`) — *not* from `project.name`, which every
profile of a multi-profile model shares and which would therefore collide. For
`model_pages/grid_basket/small/build_config.yaml` the slug is `grid_basket_small`:

```
dist/grid_basket_small/
├── grid_basket_cpl.scad          # Compiled SCAD (<source stem>_cpl.scad)
├── grid_basket_small.3mf         # Packed multi-plate 3MF (<slug>.3mf) — one plate per variant
├── variants/                     # Per-variant 3D files
│   ├── grid_basket_small_3x3x3.stl
│   └── grid_basket_small_3x3x3.3mf
├── images/                       # Rendered images
│   ├── small_3x3x3_hero.png
│   └── small_3x3x3_side.png
└── descriptions/                 # Site-specific descriptions
    ├── makerworld_description.txt
    └── printables_description.txt
```

Notes on the naming:

- **`<slug>.3mf`** is the packed file `scripts/makerworld_update.py` uploads, and its name is
  what users see on the MakerWorld profile page. Both scripts derive it from `project_slug()`
  so they always agree — see the note in `CLAUDE.md`.
- **`variants/`** holds one file per entry in each variant's `outputs:` list, named by that
  entry's `filename` (defaulting to `<variant_name>.<format>`). A model only gets per-variant
  `.3mf` files if its config asks for them: `grid_basket` declares both `stl` and `3mf`, while
  `opengrid_facade` declares `stl` only and so produces 36 STLs and no per-variant 3MF.
- **`images/`** and **`descriptions/`** are named by the `filename` / `output_file` keys in the
  `images:` and `templates.sites:` blocks, so a site with no configured output simply has no
  file there.

A **prebuilt** model (see above) produces only `descriptions/`. There is nothing to compile,
no variants to export and nothing to render, and its `.3mf` stays committed under
`model_pages/` rather than being copied into `dist/` — `makerworld_update.py` uploads it from
there.

## Advanced Usage

### Custom OpenSCAD Executable

```yaml
build:
  openscad:
    executable: "/Applications/OpenSCAD.app/Contents/MacOS/OpenSCAD"
```

### Timeout Configuration

```yaml
build:
  openscad:
    timeout: 600  # 10 minutes for complex models
  render:
    timeout: 300  # 5 minutes for image rendering
```

### Additional OpenSCAD Flags

```yaml
build:
  openscad:
    additional_flags: ["--enable=manifold", "--enable=fast-csg"]
```

## Troubleshooting

### OpenSCAD Not Found

Make sure OpenSCAD is in your PATH:
```bash
which openscad
```

Or specify the full path in your config:
```yaml
build:
  openscad:
    executable: "/full/path/to/openscad"
```

### Jinja2 Import Error

Install the required Python packages:
```bash
pip install pyyaml jinja2
```

### Timeout Errors

Increase timeout values for complex models:
```yaml
build:
  openscad:
    timeout: 600
```

### Template Rendering Issues

Check that:
1. Template files exist in `templates/sections/`
2. Section paths in config match actual file locations
3. Template syntax is valid Jinja2

## Example: Grid Basket

See `build_config.example.yaml` (at repo root) for a complete working example with:
- 3 variants (small, medium, large)
- Multiple camera angles per variant
- Both MakerWorld and Printables outputs
- Shared and site-specific content sections

## Next Steps

- [ ] Add file watching for auto-rebuild
- [ ] Support for animation rendering
- [ ] Batch processing multiple projects
- [ ] Integration with version control tags

## Contributing

When adding new template sections:
1. Add to `templates/sections/shared/` for universal content
2. Add to `templates/sections/{site}/` for site-specific content
3. Update `build_config.example.yaml` to demonstrate usage
4. Test with actual build

## License

Part of the open_source_models project. See main repository for license.