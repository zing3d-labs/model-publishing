#!/usr/bin/env python3

import os
import sys
import re
import argparse
import zipfile
from typing import Set

# Regular expression to find 'use <...>' or 'include <...>' statements.
INCLUDE_RE = re.compile(r'^\s*(use|include)\s*<\s*([^>]+)\s*>.*')

def collect_dependencies(
    filepath: str,
    processed_files: Set[str],
    files_to_zip: Set[str],
    abs_library_prefixes: Set[str]
):
    """
    Recursively finds all non-library OpenSCAD dependencies for a given file.

    Args:
        filepath (str): The absolute path to the OpenSCAD file to process.
        processed_files (Set[str]): A set of absolute filepaths already processed to prevent loops.
        files_to_zip (Set[str]): A set to collect the absolute paths of all files to be zipped.
        abs_library_prefixes (Set[str]): A set of absolute library directory paths to exclude.
    """
    filepath = os.path.abspath(filepath)
    
    # --- Loop Prevention ---
    if filepath in processed_files:
        return
    processed_files.add(filepath)

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
    except FileNotFoundError:
        print(f"WARNING: File not found and will not be included: {filepath}", file=sys.stderr)
        return

    print(f"Scanning: {filepath}")
    
    # --- Add the current file to our collection ---
    files_to_zip.add(filepath)
    
    file_dir = os.path.dirname(filepath)

    for line in lines:
        match = INCLUDE_RE.match(line)
        if not match:
            continue

        included_filename_str = match.group(2)
        included_filepath = os.path.abspath(os.path.join(file_dir, included_filename_str))

        # --- Library Check ---
        # Check if the resolved absolute path starts with a library path.
        is_library_file = any(included_filepath.startswith(prefix) for prefix in abs_library_prefixes)
        
        if is_library_file:
            print(f"  -> Skipping library file: {included_filename_str}")
            continue

        # --- Recurse into the dependency ---
        print(f"  -> Found dependency: {included_filename_str}")
        collect_dependencies(included_filepath, processed_files, files_to_zip, abs_library_prefixes)


def main():
    """Main function to parse arguments, collect files, and create a zip archive."""
    parser = argparse.ArgumentParser(
        description='Packages an OpenSCAD project and its local dependencies into a zip file.',
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""
Example Usage:
--------------
# Create a zip file from my_project.scad and its dependencies
python3 scad-packager.py my_project.scad

# Specify an output file name
python3 scad-packager.py my_project.scad -o my_project_archive.zip

# Exclude the BOSL2 library, which is in a local 'external' directory
python3 scad-packager.py my_project.scad -l external/BOSL2/
"""
    )
    
    parser.add_argument('input_file', type=str, help='The main OpenSCAD script to package.')
    parser.add_argument('-o', '--output', type=str, help='Path for the output zip file. (default: <input>_source.zip)')
    parser.add_argument(
        '-l', '--library',
        action='append',
        dest='libraries',
        default=[],
        help='A library path prefix to exclude from the zip file (e.g., "external/BOSL2/"). Path is relative to the current directory.'
    )

    args = parser.parse_args()
    
    # --- Determine Output File ---
    output_file = args.output or f"{os.path.splitext(args.input_file)[0]}_source.zip"

    # --- Initialize Sets ---
    processed_files = set()
    files_to_zip = set()
    # Convert library prefixes to absolute paths for reliable comparison
    abs_library_prefixes = {os.path.abspath(p) for p in args.libraries}

    print("--- OpenSCAD Project Packager ---")
    if abs_library_prefixes:
        print(f"Excluding library paths: {', '.join(abs_library_prefixes)}")
    
    # --- Collect all file dependencies ---
    collect_dependencies(args.input_file, processed_files, files_to_zip, abs_library_prefixes)
    
    if not files_to_zip:
        print("\nNo files found to package. Exiting.")
        sys.exit(0)

    # --- Create the Zip Archive ---
    print(f"\nFound {len(files_to_zip)} file(s) to package.")
    try:
        # Find the common base directory of all files to create a clean zip structure
        common_base_path = os.path.dirname(os.path.commonprefix(list(files_to_zip)))
        
        with zipfile.ZipFile(output_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for file_path in files_to_zip:
                # Calculate the path inside the zip file to preserve directory structure
                archive_name = os.path.relpath(file_path, common_base_path)
                print(f"  + Adding: {archive_name}")
                zipf.write(file_path, arcname=archive_name)
                
        print(f"\n✅ Packaging successful! Output saved to: {output_file}")

    except Exception as e:
        print(f"\n❌ Error creating zip file: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
