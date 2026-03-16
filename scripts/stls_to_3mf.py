#!/usr/bin/env python3
"""
Pack multiple STL files into a Bambu Studio-compatible 3MF file.
One STL per build plate, with each plate named after the STL (stem).

Usage:
    stls_to_3mf.py -o output.3mf file1.stl file2.stl ...
    stls_to_3mf.py -o output.3mf --plate-names "2x2" "2x3" file1.stl file2.stl ...
"""

import math
import os
import struct
import zipfile
import zlib
import uuid
import argparse
from datetime import date
from pathlib import Path
from typing import List, Tuple, Optional

# Bambu plate layout constants (P1S: 256x256mm bed)
PLATE_SPACING = 307.2   # mm between plate centers
FIRST_PLATE_X = 128.0
FIRST_PLATE_Y = 128.0


def plate_cols(n: int) -> int:
    """Number of columns Bambu Studio uses for n plates: ceil(sqrt(n)), max 6."""
    return min(6, math.ceil(math.sqrt(n)))


# ── PNG generation ───────────────────────────────────────────────────────────

def make_placeholder_png(width: int, height: int) -> bytes:
    """Generate a minimal solid-white PNG at the given dimensions."""
    def chunk(ctype: bytes, data: bytes) -> bytes:
        raw = ctype + data
        return struct.pack('>I', len(data)) + raw + struct.pack('>I', zlib.crc32(raw) & 0xffffffff)

    signature = b'\x89PNG\r\n\x1a\n'
    ihdr = chunk(b'IHDR', struct.pack('>IIBBBBB', width, height, 8, 2, 0, 0, 0))
    scanline = b'\x00' + b'\xff\xff\xff' * width   # filter=None + white RGB pixels
    idat = chunk(b'IDAT', zlib.compress(scanline * height, 1))
    iend = chunk(b'IEND', b'')
    return signature + ihdr + idat + iend


# ── STL parsing ─────────────────────────────────────────────────────────────

def parse_stl(filepath: str):
    """Parse a binary STL. Returns (vertices, triangles, z_min)."""
    with open(filepath, 'rb') as f:
        f.read(80)  # header
        count = struct.unpack('<I', f.read(4))[0]

        vertex_map = {}
        vertices = []
        triangles = []

        for _ in range(count):
            f.read(12)  # skip normal vector
            tri = []
            for _ in range(3):
                x, y, z = struct.unpack('<3f', f.read(12))
                key = (round(x, 5), round(y, 5), round(z, 5))
                if key not in vertex_map:
                    vertex_map[key] = len(vertices)
                    vertices.append(key)
                tri.append(vertex_map[key])
            f.read(2)  # attribute bytes
            triangles.append(tri)

    z_min = min(v[2] for v in vertices) if vertices else 0.0
    if vertices:
        x_center = (min(v[0] for v in vertices) + max(v[0] for v in vertices)) / 2
        y_center = (min(v[1] for v in vertices) + max(v[1] for v in vertices)) / 2
    else:
        x_center = y_center = 0.0
    return vertices, triangles, z_min, x_center, y_center


# ── XML generators ───────────────────────────────────────────────────────────

def make_content_types():
    return '''<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
 <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
 <Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/>
 <Default Extension="png" ContentType="image/png"/>
 <Default Extension="gcode" ContentType="text/x.gcode"/>
</Types>'''


def make_root_rels():
    return '''<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
 <Relationship Target="/3D/3dmodel.model" Id="rel-1" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>
 <Relationship Target="/Metadata/plate_1.png" Id="rel-2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/thumbnail"/>
 <Relationship Target="/Metadata/plate_1.png" Id="rel-4" Type="http://schemas.bambulab.com/package/2021/cover-thumbnail-middle"/>
 <Relationship Target="/Metadata/plate_1_small.png" Id="rel-5" Type="http://schemas.bambulab.com/package/2021/cover-thumbnail-small"/>
</Relationships>'''


def make_model_rels(n: int):
    lines = ['<?xml version="1.0" encoding="UTF-8"?>',
             '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">']
    for i in range(1, n + 1):
        lines.append(
            f' <Relationship Target="/3D/Objects/object_{i}.model" Id="rel-{i}" '
            f'Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/>'
        )
    lines.append('</Relationships>')
    return '\n'.join(lines)


def make_object_model(vertices, triangles, inner_id: int):
    """XML for a single 3D/Objects/object_N.model file."""
    obj_uuid = str(uuid.uuid4())
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<model unit="millimeter" xml:lang="en-US"'
        ' xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02"'
        ' xmlns:BambuStudio="http://schemas.bambulab.com/package/2021"'
        ' xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06"'
        ' requiredextensions="p">',
        ' <metadata name="BambuStudio:3mfVersion">1</metadata>',
        ' <resources>',
        f'  <object id="{inner_id}" p:UUID="{obj_uuid}" type="model">',
        '   <mesh>',
        '    <vertices>',
    ]
    for x, y, z in vertices:
        lines.append(f'     <vertex x="{x:.6f}" y="{y:.6f}" z="{z:.6f}"/>')
    lines += [
        '    </vertices>',
        '    <triangles>',
    ]
    for v1, v2, v3 in triangles:
        lines.append(f'     <triangle v1="{v1}" v2="{v2}" v3="{v3}"/>')
    lines += [
        '    </triangles>',
        '   </mesh>',
        '  </object>',
        ' </resources>',
        '</model>',
    ]
    return '\n'.join(lines)


def make_main_model(n: int, z_offsets: List[float], xy_centers: List[Tuple[float, float]],
                    cols: int = 0):
    """XML for 3D/3dmodel.model — wrapper objects + build items."""
    build_uuid = str(uuid.uuid4())
    today = date.today().isoformat()

    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<model unit="millimeter" xml:lang="en-US"'
        ' xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02"'
        ' xmlns:BambuStudio="http://schemas.bambulab.com/package/2021"'
        ' xmlns:p="http://schemas.microsoft.com/3dmanufacturing/production/2015/06"'
        ' requiredextensions="p">',
        f' <metadata name="Application">BambuStudio-02.04.00.70</metadata>',
        f' <metadata name="BambuStudio:3mfVersion">1</metadata>',
        f' <metadata name="CreationDate">{today}</metadata>',
        ' <resources>',
    ]

    for i in range(n):
        inner_id = 2 * i + 1   # 1, 3, 5, ...
        outer_id = 2 * i + 2   # 2, 4, 6, ...
        obj_uuid = str(uuid.uuid4())
        comp_uuid = str(uuid.uuid4())
        lines += [
            f'  <object id="{outer_id}" p:UUID="{obj_uuid}" type="model">',
            '   <components>',
            f'    <component p:path="/3D/Objects/object_{i+1}.model"'
            f' objectid="{inner_id}" p:UUID="{comp_uuid}"'
            f' transform="1 0 0 0 1 0 0 0 1 0 0 0"/>',
            '   </components>',
            '  </object>',
        ]

    lines.append(' </resources>')
    lines.append(f' <build p:UUID="{build_uuid}">')

    num_cols = cols if cols > 0 else plate_cols(n)
    for i in range(n):
        outer_id = 2 * i + 2
        item_uuid = str(uuid.uuid4())
        col = i % num_cols
        row = i // num_cols
        cx = FIRST_PLATE_X + col * PLATE_SPACING
        cy = FIRST_PLATE_Y - row * PLATE_SPACING
        tx = cx - xy_centers[i][0]
        ty = cy - xy_centers[i][1]
        z = z_offsets[i]
        lines.append(
            f'  <item objectid="{outer_id}" p:UUID="{item_uuid}"'
            f' transform="1 0 0 0 1 0 0 0 1 {tx:.6f} {ty:.6f} {z:.6f}" printable="1"/>'
        )

    lines += [' </build>', '</model>']
    return '\n'.join(lines)


def make_model_settings(stl_paths: List[str], plate_names: List[str],
                        face_counts: List[int], z_offsets: List[float]):
    """XML for Metadata/model_settings.config."""
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<config>']

    for i, (stl_path, face_count, z_off) in enumerate(zip(stl_paths, face_counts, z_offsets)):
        outer_id = 2 * i + 2
        inner_id = 2 * i + 1
        stem = Path(stl_path).stem
        lines += [
            f'  <object id="{outer_id}">',
            f'    <metadata key="name" value="{stem}"/>',
            f'    <metadata key="extruder" value="1"/>',
            f'    <metadata face_count="{face_count}"/>',
            f'    <part id="{inner_id}" subtype="normal_part">',
            f'      <metadata key="name" value="{stem}"/>',
            f'      <metadata key="matrix" value="1 0 0 0 0 1 0 0 0 0 1 0 0 0 0 1"/>',
            f'      <metadata key="source_file" value="{Path(stl_path).name}"/>',
            f'      <metadata key="source_object_id" value="0"/>',
            f'      <metadata key="source_volume_id" value="0"/>',
            f'      <metadata key="source_offset_x" value="0"/>',
            f'      <metadata key="source_offset_y" value="0"/>',
            f'      <metadata key="source_offset_z" value="{z_off:.6f}"/>',
            f'      <mesh_stat face_count="{face_count}" edges_fixed="0"'
            f' degenerate_facets="0" facets_removed="0" facets_reversed="0" backwards_edges="0"/>',
            f'    </part>',
            f'  </object>',
        ]

    for i, (plate_name, stl_path) in enumerate(zip(plate_names, stl_paths)):
        outer_id = 2 * i + 2
        plate_num = i + 1
        identify_id = (i + 1) * 44 + 37  # matches Bambu's pattern
        lines += [
            '  <plate>',
            f'    <metadata key="plater_id" value="{plate_num}"/>',
            f'    <metadata key="plater_name" value="{plate_name}"/>',
            f'    <metadata key="locked" value="false"/>',
            f'    <metadata key="filament_map_mode" value="Auto For Flush"/>',
            f'    <metadata key="thumbnail_file" value="Metadata/plate_{plate_num}.png"/>',
            f'    <metadata key="thumbnail_no_light_file" value="Metadata/plate_no_light_{plate_num}.png"/>',
            f'    <metadata key="top_file" value="Metadata/top_{plate_num}.png"/>',
            f'    <metadata key="pick_file" value="Metadata/pick_{plate_num}.png"/>',
            '    <model_instance>',
            f'      <metadata key="object_id" value="{outer_id}"/>',
            f'      <metadata key="instance_id" value="0"/>',
            f'      <metadata key="identify_id" value="{identify_id}"/>',
            '    </model_instance>',
            '  </plate>',
        ]

    lines.append('</config>')
    return '\n'.join(lines)


def make_slice_info():
    return '''<?xml version="1.0" encoding="UTF-8"?>
<config>
  <header>
    <header_item key="X-BBL-Client-Type" value="slicer"/>
    <header_item key="X-BBL-Client-Version" value="02.04.00.70"/>
  </header>
</config>'''


def make_project_settings() -> str:
    """Load project settings from bundled P1S profile."""
    profile = Path(__file__).parent / 'project_settings_p1s.config'
    if profile.exists():
        return profile.read_text()
    import json
    return json.dumps({"version": "02.04.00.70"}, indent=4)


# ── Main packer ──────────────────────────────────────────────────────────────

def pack(stl_files: List[str], output_path: str,
         plate_names: Optional[List[str]] = None):
    """Pack STL files into a Bambu Studio 3MF, one per plate."""
    if plate_names is None:
        plate_names = [Path(f).stem for f in stl_files]

    if len(plate_names) != len(stl_files):
        raise ValueError("plate_names length must match stl_files length")

    if len(stl_files) > 36:
        raise ValueError("Bambu Studio supports a maximum of 36 plates")

    print(f"Packing {len(stl_files)} STLs into {output_path}")

    # Parse all STLs
    meshes = []
    for stl_path in stl_files:
        print(f"  Parsing: {Path(stl_path).name}")
        verts, tris, z_min, x_center, y_center = parse_stl(stl_path)
        meshes.append((verts, tris, z_min, x_center, y_center))

    z_offsets = [-m[2] for m in meshes]   # -z_min so model sits on bed
    xy_centers = [(m[3], m[4]) for m in meshes]
    face_counts = [len(m[1]) for m in meshes]

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    with zipfile.ZipFile(output_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('[Content_Types].xml', make_content_types())
        zf.writestr('_rels/.rels', make_root_rels())
        zf.writestr('3D/_rels/3dmodel.model.rels', make_model_rels(len(stl_files)))
        cols = plate_cols(len(stl_files))
        zf.writestr('3D/3dmodel.model',
                    make_main_model(len(stl_files), z_offsets, xy_centers, cols))

        for i, (verts, tris, _, __, ___) in enumerate(meshes):
            inner_id = 2 * i + 1
            zf.writestr(f'3D/Objects/object_{i+1}.model',
                        make_object_model(verts, tris, inner_id))

        zf.writestr('Metadata/model_settings.config',
                    make_model_settings(stl_files, plate_names,
                                        face_counts, z_offsets))
        zf.writestr('Metadata/slice_info.config', make_slice_info())
        zf.writestr('Metadata/project_settings.config', make_project_settings())

        # Plate thumbnail images (placeholder white PNGs — Bambu Studio needs these
        # to treat the file as current format rather than falling back to geometry-only)
        png_512 = make_placeholder_png(512, 512)
        png_128 = make_placeholder_png(128, 128)
        for i in range(1, len(stl_files) + 1):
            zf.writestr(f'Metadata/plate_{i}.png', png_512)
            zf.writestr(f'Metadata/plate_{i}_small.png', png_128)
            zf.writestr(f'Metadata/plate_no_light_{i}.png', png_512)
            zf.writestr(f'Metadata/top_{i}.png', png_512)
            zf.writestr(f'Metadata/pick_{i}.png', png_512)

    size_mb = os.path.getsize(output_path) / 1_000_000
    print(f"Written: {output_path} ({size_mb:.1f} MB)")


# ── CLI ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='Pack STL files into a Bambu Studio 3MF, one STL per plate'
    )
    parser.add_argument('stl_files', nargs='+', help='STL files to pack')
    parser.add_argument('-o', '--output', required=True, help='Output .3mf path')
    parser.add_argument('--plate-names', nargs='+',
                        help='Plate names (defaults to STL stems)')
    args = parser.parse_args()

    pack(args.stl_files, args.output, args.plate_names)


if __name__ == '__main__':
    main()
