"""Tests for the bearer credential strategy."""

import pytest

from gapp_run.auth.strategies.bearer import get_access_token


class TestBearerStrategy:
    def test_extracts_credential_field(self):
        cred = {"strategy": "bearer", "credential": "my-token-123"}
        assert get_access_token(cred) == "my-token-123"

    def test_preserves_token_exactly(self):
        token = "test-token-exact"
        cred = {"credential": token}
        assert get_access_token(cred) == token

    def test_missing_credential_field_raises(self):
        cred = {"strategy": "bearer"}
        with pytest.raises(ValueError, match="missing 'credential' field"):
            get_access_token(cred)

    def test_empty_credential_field_raises(self):
        cred = {"strategy": "bearer", "credential": ""}
        with pytest.raises(ValueError, match="missing 'credential' field"):
            get_access_token(cred)

    def test_ignores_extra_metadata(self):
        cred = {
            "strategy": "bearer",
            "credential": "my-token",
            "sub": "user@example.com",
            "created": "2026-03-12T00:00:00Z",
        }
        assert get_access_token(cred) == "my-token"
