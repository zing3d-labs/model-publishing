#!/usr/bin/env python3
"""Print the next version string for a model based on existing git tags.

Tag format: <model>/v<major>.<minor>.<patch>

If no tags exist yet, the version already in build_config.yaml is used as the
first release (no increment). On subsequent runs, the patch number increments.

Usage: ci_next_version.py <model>
"""

import subprocess
import sys
import yaml
from pathlib import Path


def latest_tag(model: str) -> str | None:
    result = subprocess.run(
        ["git", "tag", "-l", f"{model}/v*"],
        capture_output=True,
        text=True,
        check=True,
    )
    tags = [t.strip() for t in result.stdout.splitlines() if t.strip()]
    if not tags:
        return None
    # Sort by semver numerics
    tags.sort(key=lambda t: [int(x) for x in t.split("/v", 1)[1].split(".")])
    return tags[-1]


def main() -> None:
    model = sys.argv[1]
    tag = latest_tag(model)

    if tag is None:
        # First release — use config version as-is
        config_path = Path(f"model_pages/{model}/build_config.yaml")
        with open(config_path) as f:
            config = yaml.safe_load(f)
        print(config["project"]["version"])
    else:
        version = tag.split("/v", 1)[1]
        major, minor, patch = version.split(".")
        print(f"{major}.{minor}.{int(patch) + 1}")


if __name__ == "__main__":
    main()
