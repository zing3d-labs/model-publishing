#!/usr/bin/env python3
"""Copy a generated site description to the clipboard as rich text.

Reads the markdown description output from a build, converts it to HTML,
then places it on the macOS clipboard as RTF so it pastes with formatting
into rich text editors like MakerWorld's CKEditor.

Usage:
    ./scripts/copy_description.py model_pages/grid_basket/build_config.yaml makerworld
    ./scripts/copy_description.py model_pages/grid_basket/build_config.yaml printables

The site name must match a site defined in the build config's templates.sites section.
"""

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

try:
    import markdown
except ImportError:
    print("Error: 'markdown' package required. Install with: pip install markdown")
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="Copy a site description to clipboard as rich text"
    )
    parser.add_argument("config", help="Path to build_config.yaml")
    parser.add_argument("site", help="Site name (e.g. makerworld, printables)")
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        print(f"Error: Config file not found: {config_path}")
        sys.exit(1)

    with open(config_path) as f:
        config = yaml.safe_load(f)

    # Find the output file for this site
    config_dir = config_path.parent
    sites = config.get("templates", {}).get("sites", {})
    if args.site not in sites:
        available = ", ".join(sites.keys()) if sites else "none"
        print(f"Error: Site '{args.site}' not found. Available: {available}")
        sys.exit(1)

    output_file = sites[args.site]["output_file"]

    # Resolve output path the same way scad_builder.py does:
    # root_dir / build.output_directory / project_name / output_file
    root_dir = Path(__file__).parent.parent
    project_name = config["project"]["name"].lower().replace(" ", "_")
    output_dir = config.get("build", {}).get("output_directory", "dist/")
    dist_path = root_dir / output_dir / project_name / output_file

    if not dist_path.exists():
        print(f"Error: Description file not found: {dist_path}")
        print("Have you run the build first?")
        sys.exit(1)

    # Read the description
    md_text = dist_path.read_text()

    # Strip the === FIELD === markers and only grab the description section
    # if the file uses the makerworld_base.md format
    if "=== DESCRIPTION ===" in md_text:
        # Extract just the description field
        parts = md_text.split("=== DESCRIPTION ===")
        if len(parts) > 1:
            desc = parts[1]
            # Cut off at the next === marker if present
            next_marker = desc.find("===", 3)
            if next_marker != -1:
                desc = desc[:next_marker]
            md_text = desc.strip()

    # Convert markdown to HTML
    import re

    html_body = markdown.markdown(md_text, extensions=["sane_lists"])

    # Put HTML directly on clipboard so CKEditor preserves heading block types
    html = f"<html><body>{html_body}</body></html>"

    with tempfile.NamedTemporaryFile(suffix=".html", mode="w", encoding="utf-8", delete=False) as f:
        f.write(html)
        html_path = f.name

    try:
        # Use Swift to set HTML type on clipboard via NSPasteboard
        swift_code = f'''
import AppKit
let html = try! String(contentsOfFile: "{html_path}", encoding: .utf8)
let pb = NSPasteboard.general
pb.clearContents()
pb.setData(html.data(using: .utf8)!, forType: NSPasteboard.PasteboardType.html)
'''
        subprocess.run(
            ["swift", "-e", swift_code],
            check=True,
            capture_output=True,
        )
        print(f"Copied description for '{args.site}' to clipboard as HTML")
        print(f"Source: {dist_path}")
    finally:
        Path(html_path).unlink(missing_ok=True)


if __name__ == "__main__":
    main()
