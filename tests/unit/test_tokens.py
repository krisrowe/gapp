"""Tests for gapp.sdk.tokens — JWT creation and revocation."""

import json
import time
from unittest.mock import patch, MagicMock

import jwt as pyjwt
import pytest

from gapp.sdk.tokens import create_token, revoke_tokens, DEFAULT_DURATION_DAYS


MOCK_CTX = {
    "name": "my-app",
    "project_id": "my-project",
    "repo_path": "/tmp/my-app",
}

SIGNING_KEY = "test-signing-key-value"


def _mock_run(returncode=0, stdout="", stderr=""):
    mock = MagicMock()
    mock.returncode = returncode
    mock.stdout = stdout
    mock.stderr = stderr
    return mock


class TestCreateToken:
    @patch("gapp.sdk.tokens.subprocess.run")
    @patch("gapp.sdk.tokens.resolve_solution", return_value=MOCK_CTX)
    @patch("gapp.sdk.tokens._object_exists", return_value=True)
    def test_creates_valid_jwt(self, mock_exists, mock_ctx, mock_run):
        # _get_signing_key reads from Secret Manager
        mock_run.return_value = _mock_run(stdout=SIGNING_KEY)

        result = create_token("user@example.com")

        assert result["email"] == "user@example.com"
        assert result["solution"] == "my-app"
        assert result["duration_days"] == DEFAULT_DURATION_DAYS

        # Verify the JWT is valid
        claims = pyjwt.decode(result["token"], SIGNING_KEY, algorithms=["HS256"], audience="my-app")
        assert claims["sub"] == "user@example.com"
        assert claims["aud"] == "my-app"
        assert "iat" in claims
        assert "exp" in claims

    @patch("gapp.sdk.tokens.subprocess.run")
    @patch("gapp.sdk.tokens.resolve_solution", return_value=MOCK_CTX)
    @patch("gapp.sdk.tokens._object_exists", return_value=True)
    def test_custom_duration(self, mock_exists, mock_ctx, mock_run):
        mock_run.return_value = _mock_run(stdout=SIGNING_KEY)

        result = create_token("user@example.com", duration_days=30)

        assert result["duration_days"] == 30
        claims = pyjwt.decode(result["token"], SIGNING_KEY, algorithms=["HS256"], audience="my-app")
        expected_exp = claims["iat"] + (30 * 86400)
        assert claims["exp"] == expected_exp

    @patch("gapp.sdk.tokens.subprocess.run")
    @patch("gapp.sdk.tokens.resolve_solution", return_value=MOCK_CTX)
    @patch("gapp.sdk.tokens._object_exists", return_value=False)
    def test_unregistered_user_fails(self, mock_exists, mock_ctx, mock_run):
        with pytest.raises(RuntimeError, match="not registered"):
            create_token("nobody@example.com")

    @patch("gapp.sdk.tokens.subprocess.run")
    @patch("gapp.sdk.tokens.resolve_solution", return_value=MOCK_CTX)
    @patch("gapp.sdk.tokens._object_exists", return_value=True)
    def test_missing_signing_key_fails(self, mock_exists, mock_ctx, mock_run):
        mock_run.return_value = _mock_run(returncode=1, stderr="NOT_FOUND")

        with pytest.raises(RuntimeError, match="signing key"):
            create_token("user@example.com")

    @patch("gapp.sdk.tokens.subprocess.run")
    @patch("gapp.sdk.tokens.resolve_solution", return_value=MOCK_CTX)
    @patch("gapp.sdk.tokens._object_exists", return_value=True)
    def test_default_duration_is_10_years(self, mock_exists, mock_ctx, mock_run):
        assert DEFAULT_DURATION_DAYS == 3650
        mock_run.return_value = _mock_run(stdout=SIGNING_KEY)

        result = create_token("user@example.com")
        claims = pyjwt.decode(result["token"], SIGNING_KEY, algorithms=["HS256"], audience="my-app")
        # ~10 years in seconds
        duration = claims["exp"] - claims["iat"]
        assert duration == 3650 * 86400


class TestRevokeTokens:
    @patch("gapp.sdk.tokens._write_credential")
    @patch("gapp.sdk.tokens._read_credential_full")
    @patch("gapp.sdk.tokens._object_exists", return_value=True)
    @patch("gapp.sdk.tokens.resolve_solution", return_value=MOCK_CTX)
    def test_sets_revoke_before(self, mock_ctx, mock_exists, mock_read, mock_write):
        mock_read.return_value = {
            "strategy": "bearer",
            "credential": "token",
            "sub": "user@example.com",
        }

        result = revoke_tokens("user@example.com")

        assert result["email"] == "user@example.com"
        assert "revoke_before" in result

        # Verify the credential was written with revoke_before
        written = mock_write.call_args[0][1]
        assert "revoke_before" in written
        assert written["credential"] == "token"  # preserved
        assert written["sub"] == "user@example.com"  # preserved

    @patch("gapp.sdk.tokens._object_exists", return_value=False)
    @patch("gapp.sdk.tokens.resolve_solution", return_value=MOCK_CTX)
    def test_nonexistent_user_fails(self, mock_ctx, mock_exists):
        with pytest.raises(RuntimeError, match="not found"):
            revoke_tokens("nobody@example.com")

    @patch("gapp.sdk.tokens._write_credential")
    @patch("gapp.sdk.tokens._read_credential_full")
    @patch("gapp.sdk.tokens._object_exists", return_value=True)
    @patch("gapp.sdk.tokens.resolve_solution", return_value=MOCK_CTX)
    def test_preserves_existing_fields(self, mock_ctx, mock_exists, mock_read, mock_write):
        mock_read.return_value = {
            "strategy": "google_oauth2",
            "credential": "cred-data",
            "sub": "user@example.com",
            "created": "2026-03-13T00:00:00+00:00",
        }

        revoke_tokens("user@example.com")

        written = mock_write.call_args[0][1]
        assert written["strategy"] == "google_oauth2"
        assert written["created"] == "2026-03-13T00:00:00+00:00"
