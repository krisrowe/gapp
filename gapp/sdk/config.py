"""Configuration and path resolution for gapp."""

import os
from pathlib import Path

import yaml


def get_config_dir() -> Path:
    """Return the gapp config directory, respecting XDG_CONFIG_HOME."""
    base = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
    return Path(base) / "gapp"


def get_solutions_file() -> Path:
    """Return the path to solutions.yaml."""
    return get_config_dir() / "solutions.yaml"


def load_solutions() -> dict:
    """Load the solutions registry. Returns empty dict if file doesn't exist."""
    path = get_solutions_file()
    if not path.exists():
        return {}
    with open(path) as f:
        return yaml.safe_load(f) or {}


def save_solutions(solutions: dict) -> None:
    """Save the solutions registry."""
    path = get_solutions_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(solutions, f, default_flow_style=False)
