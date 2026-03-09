"""Tests for gapp.sdk.solutions — solution listing and discovery."""

from unittest.mock import patch

from gapp.sdk.config import save_solutions
from gapp.sdk.solutions import list_solutions


def test_list_empty():
    assert list_solutions() == []


def test_list_local_solutions():
    save_solutions({
        "app-a": {"repo_path": "/tmp/app-a", "project_id": "proj-a"},
        "app-b": {"repo_path": "/tmp/app-b"},
    })
    results = list_solutions()
    assert len(results) == 2
    names = {r["name"] for r in results}
    assert names == {"app-a", "app-b"}
    assert all(r["source"] == "local" for r in results)


@patch("gapp.sdk.solutions._discover_github_solutions", return_value=[
    {"name": "remote-app", "project_id": None, "repo_path": None,
     "url": "https://github.com/user/remote-app", "source": "github"},
])
def test_list_with_remote(mock_discover):
    save_solutions({"local-app": {"repo_path": "/tmp/local-app"}})
    results = list_solutions(include_remote=True)
    names = {r["name"] for r in results}
    assert "local-app" in names
    assert "remote-app" in names


@patch("gapp.sdk.solutions._discover_github_solutions", return_value=[
    {"name": "overlap", "project_id": None, "repo_path": None,
     "url": "https://github.com/user/overlap", "source": "github"},
])
def test_remote_deduplicates_with_local(mock_discover):
    save_solutions({"overlap": {"repo_path": "/tmp/overlap"}})
    results = list_solutions(include_remote=True)
    overlap_entries = [r for r in results if r["name"] == "overlap"]
    assert len(overlap_entries) == 1
    assert overlap_entries[0]["source"] == "local"
