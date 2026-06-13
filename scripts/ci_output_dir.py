#!/usr/bin/env python3
"""Print the descriptions output directory for a model.

Mirrors the path logic in SCADBuilder: project name is lowercased with spaces
replaced by underscores, nested under the configured output_directory.

Usage: ci_output_dir.py <model>
"""

import sys
import yaml
from pathlib import Path


def main() -> None:
    model = sys.argv[1]
    config_path = Path(f"model_pages/{model}/build_config.yaml")

    with open(config_path) as f:
        config = yaml.safe_load(f)

    project_name = config["project"]["name"].lower().replace(" ", "_")
    output_dir = config["build"]["output_directory"].rstrip("/")
    print(f"{output_dir}/{project_name}/descriptions")


if __name__ == "__main__":
    main()
