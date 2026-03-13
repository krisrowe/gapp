"""Tests for gapp.sdk.config — XDG config management."""

from pathlib import Path

from gapp.admin.sdk.config import get_config_dir, load_solutions, save_solutions


def test_config_dir_uses_xdg(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    result = get_config_dir()
    assert result == tmp_path / "gapp"


def test_config_dir_defaults_to_home(tmp_path, monkeypatch):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path))
    result = get_config_dir()
    assert result == tmp_path / ".config" / "gapp"


def test_load_solutions_empty():
    """No solutions.yaml yet — returns empty dict."""
    result = load_solutions()
    assert result == {}


def test_save_and_load_roundtrip():
    solutions = {
        "my-app": {"repo_path": "/tmp/my-app", "project_id": "my-project"},
        "other": {"repo_path": "/tmp/other"},
    }
    save_solutions(solutions)
    loaded = load_solutions()
    assert loaded == solutions


def test_save_creates_config_dir():
    """save_solutions creates the config directory if it doesn't exist."""
    config_dir = get_config_dir()
    assert not config_dir.exists()
    save_solutions({"test": {}})
    assert config_dir.exists()
    assert (config_dir / "solutions.yaml").exists()
