"""Parse and validate deploy/manifest.yaml files."""

from pathlib import Path

import yaml


def load_manifest(repo_path: Path) -> dict:
    """Load deploy/manifest.yaml from a repo. Returns empty dict if missing."""
    manifest_path = repo_path / "deploy" / "manifest.yaml"
    if not manifest_path.exists():
        return {}
    with open(manifest_path) as f:
        return yaml.safe_load(f) or {}


def get_solution_name(manifest: dict, repo_path: Path) -> str:
    """Derive solution name from manifest or repo directory name."""
    solution = manifest.get("solution", {})
    return solution.get("name", repo_path.name)


def get_prerequisite_secrets(manifest: dict) -> dict:
    """Return prerequisite secrets from the manifest."""
    return manifest.get("prerequisites", {}).get("secrets", {})


def get_required_apis(manifest: dict) -> list:
    """Return required GCP APIs from the manifest."""
    return manifest.get("prerequisites", {}).get("apis", [])
