#!/usr/bin/env python3
"""Patch the project.version field in a build_config.yaml in-place.

Preserves all formatting and comments in the file.

Usage: ci_patch_version.py <model> <version>
"""

import re
import sys


def main() -> None:
    model, version = sys.argv[1], sys.argv[2]
    path = f"model_pages/{model}/build_config.yaml"

    with open(path) as f:
        content = f.read()

    # Replace:  version: "x.y.z"
    patched = re.sub(
        r'(?m)^(\s+version:\s+")[^"]*(")',
        lambda m: m.group(1) + version + m.group(2),
        content,
    )

    if patched == content:
        print(f"WARNING: version field not found in {path}", file=sys.stderr)
        sys.exit(1)

    with open(path, "w") as f:
        f.write(patched)

    print(f"Patched {path} → version {version}")


if __name__ == "__main__":
    main()
