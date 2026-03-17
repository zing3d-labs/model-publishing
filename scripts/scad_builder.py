#!/usr/bin/env python3
"""
OpenSCAD Build Orchestrator

This script orchestrates the complete build process for OpenSCAD projects:
1. Compiles SCAD files (inlines dependencies)
2. Generates STL/3MF files for each variant with custom parameters
3. Renders images from multiple angles
4. Generates site-specific descriptions from modular templates
"""

import os
import yaml
import subprocess
import shutil
import time
from pathlib import Path
from typing import Dict, List, Any
import argparse
import logging

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class SCADBuilder:
    """Main orchestrator for building OpenSCAD projects"""

    def __init__(self, config_path: str):
        self.config_path = Path(config_path)
        self.config_dir = self.config_path.parent
        self.config = self.load_config()
        # Get the root directory (where scripts/ is located)
        root_dir = Path(__file__).parent.parent
        project_name = self.config['project']['name'].lower().replace(' ', '_')
        self.output_dir = root_dir / self.config['build']['output_directory'] / project_name

    def load_config(self) -> Dict[str, Any]:
        """Load and validate the build configuration"""
        logger.info(f"Loading configuration from {self.config_path}")

        with open(self.config_path, 'r') as f:
            config = yaml.safe_load(f)

        # Validate required fields
        required_fields = ['project', 'source', 'variants', 'build']
        for field in required_fields:
            if field not in config:
                raise ValueError(f"Missing required config field: {field}")

        return config

    def setup_output_directories(self, clean=True):
        """Create output directory structure"""
        logger.info("Setting up output directories")

        if clean and self.config['build'].get('clean_before_build', False):
            if self.output_dir.exists():
                logger.info(f"Cleaning output directory: {self.output_dir}")
                shutil.rmtree(self.output_dir)

        # Create directory structure
        self.output_dir.mkdir(parents=True, exist_ok=True)
        (self.output_dir / 'variants').mkdir(exist_ok=True)
        (self.output_dir / 'images').mkdir(exist_ok=True)
        (self.output_dir / 'descriptions').mkdir(exist_ok=True)

    def _openscad_env(self) -> dict:
        """Return an environment dict for OpenSCAD subprocesses with OPENSCADPATH set
        from the configured libraries. For each library we add both the library dir itself
        and its parent, so that:
          - <BOSL2/std.scad> resolves via the parent dir
          - <builtins.scad> (used internally by BOSL2 files) resolves via the BOSL2 dir"""
        seen = []
        for lib in self.config['source'].get('libraries', []):
            lib_dir = (self.config_dir / lib).resolve()
            if not lib_dir.exists():
                continue
            parent = str(lib_dir.parent)
            for p in [parent, str(lib_dir)]:
                if p not in seen:
                    seen.append(p)
        env = os.environ.copy()
        if seen:
            existing = env.get('OPENSCADPATH', '')
            all_paths = seen + ([existing] if existing else [])
            env['OPENSCADPATH'] = ':'.join(all_paths)
        return env

    def compile_scad(self) -> Path:
        """Compile the main SCAD file using scad-compiler from zing3d-labs/openscad-toolkit"""
        start_time = time.time()
        logger.info("Compiling SCAD file")

        source_file = self.config_dir / self.config['source']['input_file']
        compiled_file = self.output_dir / f"{source_file.stem}_cpl.scad"

        # Build compile command using uvx with latest release
        cmd = [
            'uvx',
            '--from', 'git+https://github.com/zing3d-labs/openscad-toolkit@v0.14.0',
            'scad-compiler',
            str(source_file),
            '-o', str(compiled_file)
        ]

        # Add library prefixes
        for lib in self.config['source'].get('libraries', []):
            cmd.extend(['-l', lib])

        logger.info(f"Running: {' '.join(cmd)}")
        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode != 0:
            logger.error(f"Compilation failed: {result.stderr}")
            raise RuntimeError("SCAD compilation failed")

        elapsed = time.time() - start_time
        logger.info(f"Compiled SCAD saved to: {compiled_file} (took {elapsed:.2f}s)")
        return compiled_file

    def _variant_scad(self, compiled_scad: Path, parameters: dict) -> Path:
        """Write a variant-specific SCAD file with parameters appended after the compiled
        content. Appending ensures these assignments are last in the file and win over any
        same-named variables defined earlier (OpenSCAD last-assignment-wins semantics).
        The returned path is a sibling of compiled_scad; callers are responsible for cleanup."""
        lines = [compiled_scad.read_text(), "\n// --- variant parameters ---\n"]
        for param_name, param_value in parameters.items():
            if isinstance(param_value, bool):
                lines.append(f"{param_name} = {str(param_value).lower()};\n")
            elif isinstance(param_value, str):
                lines.append(f'{param_name} = "{param_value}";\n')
            else:
                lines.append(f"{param_name} = {param_value};\n")
        variant_scad = compiled_scad.with_suffix('.variant.scad')
        variant_scad.write_text("".join(lines))
        return variant_scad

    def generate_variant_files(self, compiled_scad: Path):
        """Generate STL/3MF files for each variant"""
        logger.info("Generating variant files")

        openscad_exec = self.config['build']['openscad']['executable']
        timeout = self.config['build']['openscad']['timeout']
        additional_flags = self.config['build']['openscad'].get('additional_flags', [])

        for variant_name, variant_config in self.config['variants'].items():
            logger.info(f"Processing variant: {variant_name}")

            variant_scad = self._variant_scad(compiled_scad, variant_config['parameters'])
            try:
                for output in variant_config['outputs']:
                    output_format = output['format']
                    output_filename = output.get('filename', f"{variant_name}.{output_format}")
                    output_path = self.output_dir / 'variants' / output_filename

                    format_flags = []
                    if output_format == 'stl':
                        stl_encoding = output.get('stl_encoding', 'binary')
                        export_format = 'asciistl' if stl_encoding == 'ascii' else 'binstl'
                        format_flags = ['--export-format', export_format]

                    cmd = [
                        openscad_exec,
                        '-o', str(output_path),
                        *additional_flags,
                        *format_flags,
                        str(variant_scad)
                    ]

                    logger.info(f"Generating {output_format.upper()}: {output_filename}")
                    logger.debug(f"Command: {' '.join(cmd)}")

                    file_start_time = time.time()
                    try:
                        result = subprocess.run(
                            cmd,
                            capture_output=True,
                            text=True,
                            timeout=timeout,
                            env=self._openscad_env()
                        )

                        file_elapsed = time.time() - file_start_time
                        if result.returncode != 0:
                            logger.error(f"Failed to generate {output_filename}: {result.stderr} (took {file_elapsed:.2f}s)")
                        else:
                            logger.info(f"Successfully generated: {output_filename} (took {file_elapsed:.2f}s)")

                    except subprocess.TimeoutExpired:
                        file_elapsed = time.time() - file_start_time
                        logger.error(f"Timeout generating {output_filename} (took {file_elapsed:.2f}s)")
            finally:
                variant_scad.unlink(missing_ok=True)

    def generate_images(self, compiled_scad: Path):
        """Generate rendered images for variants"""
        if 'images' not in self.config:
            logger.info("No image configuration found, skipping")
            return

        logger.info("Generating images")

        openscad_exec = self.config['build']['openscad']['executable']
        timeout = self.config['build'].get('render', {}).get('timeout', 120)
        additional_flags = self.config['build'].get('render', {}).get('additional_flags', [])

        defaults = self.config['images'].get('defaults', {})
        resolution = defaults.get('resolution', [1920, 1080])
        background = defaults.get('background', 'white')
        colorscheme = defaults.get('colorscheme', 'Nature')

        for view in self.config['images'].get('views', []):
            variant_name = view['variant']
            variant_config = self.config['variants'][variant_name]

            # Build parameter string for this variant, with image-level overrides applied
            image_overrides = self.config['images'].get('parameter_overrides', {})
            merged_params = {**variant_config['parameters'], **image_overrides}
            param_args = []
            for param_name, param_value in merged_params.items():
                if isinstance(param_value, bool):
                    param_args.extend(['-D', f'{param_name}={str(param_value).lower()}'])
                elif isinstance(param_value, str):
                    param_args.extend(['-D', f'{param_name}="{param_value}"'])
                else:
                    param_args.extend(['-D', f'{param_name}={param_value}'])

            for shot in view['shots']:
                camera = shot['camera']
                cam_pos = camera['position']
                cam_lookat = camera['look_at']

                # Format: camera=translatex,translatey,translatez,rotx,roty,rotz,dist
                # For position/lookat, we use: x,y,z,lookatx,lookaty,lookatz
                camera_str = f"{cam_pos[0]},{cam_pos[1]},{cam_pos[2]},{cam_lookat[0]},{cam_lookat[1]},{cam_lookat[2]}"

                output_filename = shot['filename']
                output_path = self.output_dir / 'images' / output_filename

                cmd = [
                    openscad_exec,
                    '--render',
                    f'--camera={camera_str}',
                    f'--imgsize={resolution[0]},{resolution[1]}',
                    f'--colorscheme={colorscheme}',
                    *additional_flags,
                    *param_args,
                    '-o', str(output_path),
                    str(compiled_scad)
                ]

                logger.info(f"Rendering image: {output_filename}")
                logger.debug(f"Command: {' '.join(cmd)}")

                img_start_time = time.time()
                try:
                    result = subprocess.run(
                        cmd,
                        capture_output=True,
                        text=True,
                        timeout=timeout,
                        env=self._openscad_env()
                    )

                    img_elapsed = time.time() - img_start_time
                    if result.returncode != 0:
                        logger.error(f"Failed to render {output_filename}: {result.stderr} (took {img_elapsed:.2f}s)")
                    else:
                        logger.info(f"Successfully rendered: {output_filename} (took {img_elapsed:.2f}s)")

                except subprocess.TimeoutExpired:
                    img_elapsed = time.time() - img_start_time
                    logger.error(f"Timeout rendering {output_filename} (took {img_elapsed:.2f}s)")

    def generate_descriptions(self):
        """Generate site-specific descriptions from modular templates"""
        if 'templates' not in self.config:
            logger.info("No template configuration found, skipping")
            return

        start_time = time.time()
        logger.info("Generating site-specific descriptions")

        try:
            from jinja2 import Environment, FileSystemLoader, select_autoescape
        except ImportError:
            logger.error("Jinja2 not installed. Install with: pip install jinja2")
            return

        # Setup Jinja2 environment
        # Use template_root from config if provided, otherwise default to 'templates'
        template_root = self.config['templates'].get('template_root', 'templates')
        template_dir = self.config_dir / template_root

        if not template_dir.exists():
            logger.error(f"Template directory not found: {template_dir}")
            return

        env = Environment(
            loader=FileSystemLoader([str(template_dir), str(self.config_dir)]),
            autoescape=select_autoescape(['html', 'xml']),
            trim_blocks=True,
            lstrip_blocks=True
        )

        # Process each site
        for site_name, site_config in self.config['templates']['sites'].items():
            logger.info(f"Generating description for: {site_name}")

            # Build site metadata (category, tags, model_type, source_urls, etc.)
            site_meta = {k: v for k, v in site_config.items() if k not in ('output_file', 'base_template')}

            # Canonical section list per site — all sections are optional.
            # Resolution order for each section:
            #   1. config_dir/sections/{name}.md          (model-specific override)
            #   2. sections/collections/{collection}/{name}.md  (collection default, if project.collection set)
            #   3. templates/sections/{site}/{name}.md    (site default)
            #   4. templates/sections/shared/{name}.md    (shared default)
            # Sections with no file found anywhere are silently skipped.
            canonical_sections = {
                'makerworld': [
                    'model_description', 'intro', 'print_settings', 'downloads',
                    'assembly', 'collection', 'support_project', 'related_models',
                ],
                'printables': [
                    'model_description', 'intro', 'print_settings', 'downloads',
                    'assembly', 'attribution', 'collection', 'support_project', 'related_models',
                ],
            }
            section_names = canonical_sections.get(site_name, [])
            collection = self.config['project'].get('collection')

            sections = {}
            for section_name in section_names:
                search_paths = [
                    (self.config_dir / "sections" / f"{section_name}.md",
                     f"sections/{section_name}.md"),
                ]
                if collection:
                    search_paths.append((
                        template_dir / "sections" / "collections" / collection / f"{section_name}.md",
                        f"sections/collections/{collection}/{section_name}.md",
                    ))
                search_paths += [
                    (template_dir / "sections" / site_name / f"{section_name}.md",
                     f"sections/{site_name}/{section_name}.md"),
                    (template_dir / "sections" / "shared" / f"{section_name}.md",
                     f"sections/shared/{section_name}.md"),
                ]
                template = None
                for file_path, tmpl_path in search_paths:
                    if file_path.exists():
                        template = env.get_template(tmpl_path)
                        break
                if template is None:
                    continue

                rendered = template.render(
                    project=self.config['project'],
                    variants=self.config['variants'],
                    site=site_meta
                )
                sections[section_name] = rendered

            # Use per-site base template if specified, otherwise fall back to global
            base_template_path = site_config.get('base_template', self.config['templates']['base_template'])
            base_template = env.get_template(base_template_path)
            final_output = base_template.render(
                project=self.config['project'],
                sections=sections,
                site=site_meta
            )

            # Write output file
            output_file = self.output_dir / site_config['output_file']
            output_file.parent.mkdir(parents=True, exist_ok=True)

            with open(output_file, 'w') as f:
                f.write(final_output)

            logger.info(f"Description saved to: {output_file}")

        elapsed = time.time() - start_time
        logger.info(f"Description generation completed (took {elapsed:.2f}s)")

    def pack_3mf(self):
        """Pack all STL variants into a single Bambu Studio 3MF file."""
        import sys
        scripts_dir = str(Path(__file__).parent)
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        from stls_to_3mf import pack as pack_stls

        stl_files = []
        plate_names = []

        for variant_name, variant_config in self.config['variants'].items():
            for output in variant_config['outputs']:
                if output['format'] == 'stl':
                    output_filename = output.get('filename', f"{variant_name}.stl")
                    stl_path = self.output_dir / 'variants' / output_filename
                    if stl_path.exists():
                        stl_files.append(str(stl_path))
                        plate_names.append(variant_name)
                    else:
                        logger.warning(f"STL not found, skipping from 3MF: {stl_path.name}")

        if not stl_files:
            logger.info("No STL files found, skipping 3MF packing")
            return

        project_name = self.config['project']['name'].lower().replace(' ', '_')
        output_3mf = self.output_dir / f"{project_name}.3mf"

        pack_stls(stl_files, str(output_3mf), plate_names)

    def build(self, descriptions_only=False, images_only=False):
        """Run the complete build process"""
        total_start_time = time.time()
        logger.info(f"Starting build for project: {self.config['project']['name']}")

        try:
            # Step 1: Setup (don't clean existing outputs when only generating descriptions or images)
            self.setup_output_directories(clean=not (descriptions_only or images_only))

            if not descriptions_only:
                if images_only:
                    # For images-only, we need the compiled SCAD but skip STL/3MF generation
                    compiled_scad = self.compile_scad()
                    self.generate_images(compiled_scad)
                else:
                    # Step 2: Compile SCAD
                    compiled_scad = self.compile_scad()

                    # Step 3: Generate variant files
                    self.generate_variant_files(compiled_scad)

                    # Step 4: Pack 3MF
                    self.pack_3mf()

                    # Step 5: Generate images
                    self.generate_images(compiled_scad)

            if not images_only:
                # Step 6: Generate descriptions
                self.generate_descriptions()

            total_elapsed = time.time() - total_start_time
            logger.info(f"Build completed successfully! (total time: {total_elapsed:.2f}s)")

        except Exception as e:
            total_elapsed = time.time() - total_start_time
            logger.error(f"Build failed after {total_elapsed:.2f}s: {e}")
            raise


def main():
    parser = argparse.ArgumentParser(
        description="Build OpenSCAD projects with variants, images, and site-specific descriptions"
    )
    parser.add_argument(
        'config',
        help='Path to build configuration YAML file'
    )
    parser.add_argument(
        '-v', '--verbose',
        action='store_true',
        help='Enable verbose logging'
    )
    parser.add_argument(
        '-d', '--descriptions-only',
        action='store_true',
        help='Only generate descriptions, skip SCAD compile and STL/image generation'
    )
    parser.add_argument(
        '-i', '--images-only',
        action='store_true',
        help='Only generate images, skip STL/3MF generation and descriptions'
    )

    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(logging.DEBUG)

    builder = SCADBuilder(args.config)
    builder.build(descriptions_only=args.descriptions_only, images_only=args.images_only)


if __name__ == '__main__':
    main()
