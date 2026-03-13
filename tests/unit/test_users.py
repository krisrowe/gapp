"""Tests for gapp.sdk.users — user management via GCS credential files."""

import hashlib
import json
from unittest.mock import patch, MagicMock

import pytest

from gapp.admin.sdk.users import (
    register_user,
    list_users,
    revoke_user,
    update_user,
    _email_hash,
    _gcs_path,
)


MOCK_CTX = {
    "name": "my-app",
    "project_id": "my-project",
    "repo_path": "/tmp/my-app",
}


def _mock_subprocess_run(returncode=0, stdout="", stderr=""):
    mock = MagicMock()
    mock.returncode = returncode
    mock.stdout = stdout
    mock.stderr = stderr
    return mock


class TestHelpers:
    def test_email_hash_consistent(self):
        assert _email_hash("user@example.com") == _email_hash("user@example.com")

    def test_email_hash_case_insensitive(self):
        assert _email_hash("User@Example.com") == _email_hash("user@example.com")

    def test_email_hash_strips_whitespace(self):
        assert _email_hash("  user@example.com  ") == _email_hash("user@example.com")

    def test_gcs_path(self):
        path = _gcs_path("my-bucket", "abc123")
        assert path == "gs://my-bucket/auth/abc123.json"


class TestRegisterUser:
    @patch("gapp.admin.sdk.users.subprocess.run")
    @patch("gapp.admin.sdk.users.resolve_solution", return_value=MOCK_CTX)
    def test_registers_new_user(self, mock_ctx, mock_run):
        # stat returns 1 (not found), cp returns 0 (success)
        mock_run.side_effect = [
            _mock_subprocess_run(returncode=1),  # stat — not exists
            _mock_subprocess_run(returncode=0),  # cp — write
        ]

        result = register_user("user@example.com", "my-token")

        assert result["email"] == "user@example.com"
        assert result["strategy"] == "bearer"
        assert result["email_hash"] == _email_hash("user@example.com")

        # Verify the write call
        write_call = mock_run.call_args_list[1]
        written = json.loads(write_call.kwargs.get("input", ""))
        assert written["credential"] == "my-token"
        assert written["sub"] == "user@example.com"
        assert written["strategy"] == "bearer"

    @patch("gapp.admin.sdk.users.subprocess.run")
    @patch("gapp.admin.sdk.users.resolve_solution", return_value=MOCK_CTX)
    def test_rejects_duplicate_user(self, mock_ctx, mock_run):
        mock_run.return_value = _mock_subprocess_run(returncode=0)  # stat — exists

        with pytest.raises(RuntimeError, match="already registered"):
            register_user("user@example.com", "my-token")

    @patch("gapp.admin.sdk.users.subprocess.run")
    @patch("gapp.admin.sdk.users.resolve_solution", return_value=MOCK_CTX)
    def test_custom_strategy(self, mock_ctx, mock_run):
        mock_run.side_effect = [
            _mock_subprocess_run(returncode=1),  # stat
            _mock_subprocess_run(returncode=0),  # cp
        ]

        result = register_user("user@example.com", "cred-data", strategy="google_oauth2")
        assert result["strategy"] == "google_oauth2"


class TestListUsers:
    @patch("gapp.admin.sdk.users.subprocess.run")
    @patch("gapp.admin.sdk.users.resolve_solution", return_value=MOCK_CTX)
    def test_lists_users(self, mock_ctx, mock_run):
        eh = _email_hash("user@example.com")
        cred = json.dumps({
            "sub": "user@example.com",
            "strategy": "bearer",
            "credential": "secret",
            "created": "2026-03-13T00:00:00+00:00",
        })
        mock_run.side_effect = [
            _mock_subprocess_run(stdout=f"gs://bucket/auth/{eh}.json\n"),  # ls
            _mock_subprocess_run(stdout=cred),  # cat
        ]

        result = list_users()

        assert result["total"] == 1
        assert len(result["users"]) == 1
        assert result["users"][0]["sub"] == "user@example.com"
        # credential value should NOT be in metadata
        assert "credential" not in result["users"][0]

    @patch("gapp.admin.sdk.users.subprocess.run")
    @patch("gapp.admin.sdk.users.resolve_solution", return_value=MOCK_CTX)
    def test_empty_bucket(self, mock_ctx, mock_run):
        mock_run.return_value = _mock_subprocess_run(returncode=1)  # ls fails

        result = list_users()
        assert result["total"] == 0
        assert result["users"] == []

    @patch("gapp.admin.sdk.users.subprocess.run")
    @patch("gapp.admin.sdk.users.resolve_solution", return_value=MOCK_CTX)
    def test_pagination_limit(self, mock_ctx, mock_run):
        paths = "\n".join(f"gs://bucket/auth/hash{i}.json" for i in range(5))
        cred = json.dumps({"sub": "u", "strategy": "bearer", "created": ""})
        mock_run.side_effect = [
            _mock_subprocess_run(stdout=paths),  # ls
            _mock_subprocess_run(stdout=cred),  # cat for hash0
            _mock_subprocess_run(stdout=cred),  # cat for hash1
        ]

        result = list_users(limit=2)

        assert result["total"] == 5
        assert len(result["users"]) == 2

    @patch("gapp.admin.sdk.users.subprocess.run")
    @patch("gapp.admin.sdk.users.resolve_solution", return_value=MOCK_CTX)
    def test_pagination_start_index(self, mock_ctx, mock_run):
        paths = "\n".join(f"gs://bucket/auth/hash{i}.json" for i in range(5))
        cred = json.dumps({"sub": "u", "strategy": "bearer", "created": ""})
        mock_run.side_effect = [
            _mock_subprocess_run(stdout=paths),  # ls
            _mock_subprocess_run(stdout=cred),  # cat for hash3
            _mock_subprocess_run(stdout=cred),  # cat for hash4
        ]

        result = list_users(limit=10, start_index=3)

        assert result["total"] == 5
        assert len(result["users"]) == 2


class TestUpdateUser:
    @patch("gapp.admin.sdk.users.subprocess.run")
    @patch("gapp.admin.sdk.users.resolve_solution", return_value=MOCK_CTX)
    def test_updates_credential(self, mock_ctx, mock_run):
        existing = json.dumps({
            "strategy": "bearer",
            "credential": "old-token",
            "sub": "user@example.com",
            "created": "2026-03-13T00:00:00+00:00",
        })
        mock_run.side_effect = [
            _mock_subprocess_run(returncode=0),  # stat — exists
            _mock_subprocess_run(stdout=existing),  # cat — read
            _mock_subprocess_run(returncode=0),  # cp — write
        ]

        result = update_user("user@example.com", credential="new-token")

        assert "credential" in result["changes"]
        write_call = mock_run.call_args_list[2]
        written = json.loads(write_call.kwargs.get("input", ""))
        assert written["credential"] == "new-token"
        assert written["sub"] == "user@example.com"  # preserved

    @patch("gapp.admin.sdk.users.subprocess.run")
    @patch("gapp.admin.sdk.users.resolve_solution", return_value=MOCK_CTX)
    def test_sets_revoke_before(self, mock_ctx, mock_run):
        existing = json.dumps({
            "strategy": "bearer",
            "credential": "token",
            "sub": "user@example.com",
            "created": "2026-03-13T00:00:00+00:00",
        })
        mock_run.side_effect = [
            _mock_subprocess_run(returncode=0),  # stat
            _mock_subprocess_run(stdout=existing),  # cat
            _mock_subprocess_run(returncode=0),  # cp
        ]

        result = update_user("user@example.com", revoke_before="2026-03-15T14:30:00Z")

        assert "revoke_before" in result["changes"]
        write_call = mock_run.call_args_list[2]
        written = json.loads(write_call.kwargs.get("input", ""))
        assert written["revoke_before"] == "2026-03-15T14:30:00Z"
        assert written["credential"] == "token"  # unchanged

    @patch("gapp.admin.sdk.users.subprocess.run")
    @patch("gapp.admin.sdk.users.resolve_solution", return_value=MOCK_CTX)
    def test_updates_both(self, mock_ctx, mock_run):
        existing = json.dumps({
            "strategy": "bearer",
            "credential": "old",
            "sub": "user@example.com",
            "created": "2026-03-13T00:00:00+00:00",
        })
        mock_run.side_effect = [
            _mock_subprocess_run(returncode=0),  # stat
            _mock_subprocess_run(stdout=existing),  # cat
            _mock_subprocess_run(returncode=0),  # cp
        ]

        result = update_user(
            "user@example.com",
            credential="new",
            revoke_before="2026-03-15T00:00:00Z",
        )

        assert set(result["changes"]) == {"credential", "revoke_before"}

    @patch("gapp.admin.sdk.users.subprocess.run")
    @patch("gapp.admin.sdk.users.resolve_solution", return_value=MOCK_CTX)
    def test_update_nonexistent_user_fails(self, mock_ctx, mock_run):
        mock_run.return_value = _mock_subprocess_run(returncode=1)  # stat — not found

        with pytest.raises(RuntimeError, match="not found"):
            update_user("nobody@example.com", credential="x")

    @patch("gapp.admin.sdk.users.subprocess.run")
    @patch("gapp.admin.sdk.users.resolve_solution", return_value=MOCK_CTX)
    def test_update_nothing_fails(self, mock_ctx, mock_run):
        existing = json.dumps({"strategy": "bearer", "credential": "x", "sub": "u"})
        mock_run.side_effect = [
            _mock_subprocess_run(returncode=0),  # stat
            _mock_subprocess_run(stdout=existing),  # cat
        ]

        with pytest.raises(RuntimeError, match="Nothing to update"):
            update_user("u")


class TestRevokeUser:
    @patch("gapp.admin.sdk.users.subprocess.run")
    @patch("gapp.admin.sdk.users.resolve_solution", return_value=MOCK_CTX)
    def test_revokes_existing_user(self, mock_ctx, mock_run):
        mock_run.side_effect = [
            _mock_subprocess_run(returncode=0),  # stat — exists
            _mock_subprocess_run(returncode=0),  # rm — success
        ]

        result = revoke_user("user@example.com")

        assert result["status"] == "revoked"
        assert result["email"] == "user@example.com"

    @patch("gapp.admin.sdk.users.subprocess.run")
    @patch("gapp.admin.sdk.users.resolve_solution", return_value=MOCK_CTX)
    def test_revoke_nonexistent_user_fails(self, mock_ctx, mock_run):
        mock_run.return_value = _mock_subprocess_run(returncode=1)  # stat — not found

        with pytest.raises(RuntimeError, match="not found"):
            revoke_user("nobody@example.com")
