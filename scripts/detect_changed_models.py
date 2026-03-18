#!/usr/bin/env python3
"""
Detect which model configs need to be rebuilt based on changed files.

Compares HEAD^ to HEAD and maps changed paths to affected model directories.
Outputs a JSON array suitable for use as a GitHub Actions matrix input.

Rules:
  - model_pages/<model>/**  → that specific model
  - templates/**            → all models (shared templates affect all descriptions)
  - scripts/**              → all models (build tooling changes affect all)
  - models (submodule)      → all models (source changes affect all)
"""

import json
import subprocess
import sys
from pathlib import Path


def get_changed_files() -> list[str]:
    base = subprocess.run(
        ["git", "merge-base", "origin/main", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    result = subprocess.run(
        ["git", "diff", "--name-only", base, "HEAD"],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout.splitlines()


def get_all_models() -> list[str]:
    model_pages = Path("model_pages")
    return sorted(
        d.name
        for d in model_pages.iterdir()
        if d.is_dir() and (d / "build_config.yaml").exists()
    )


def detect_changed_models(changed_files: list[str]) -> list[str]:
    all_models = get_all_models()

    # These paths affect every model's output
    global_prefixes = ("templates", "scripts", "models")

    for path in changed_files:
        if any(path == prefix or path.startswith(prefix + "/") for prefix in global_prefixes):
            return all_models

    # Otherwise collect only the directly touched model directories
    changed: list[str] = []
    for path in changed_files:
        parts = path.split("/")
        if len(parts) >= 2 and parts[0] == "model_pages":
            model = parts[1]
            if model in all_models and model not in changed:
                changed.append(model)

    return changed


def main() -> None:
    try:
        changed_files = get_changed_files()
    except subprocess.CalledProcessError as exc:
        # On the very first commit there is no HEAD^ — treat as all models changed
        print(json.dumps(get_all_models()))
        return

    models = detect_changed_models(changed_files)
    print(json.dumps(models))


if __name__ == "__main__":
    main()
