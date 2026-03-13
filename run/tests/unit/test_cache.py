"""Tests for the two-layer credential cache."""

import json
import time

import pytest

from gapp_run.auth.cache import CredentialCache, CACHE_TTL


class TestCredentialCache:
    @pytest.fixture
    def auth_mount(self, tmp_path):
        return str(tmp_path)

    def _write_cred(self, auth_mount, email_hash, data):
        path = f"{auth_mount}/{email_hash}.json"
        with open(path, "w") as f:
            json.dump(data, f)

    def test_bearer_returns_token(self, auth_mount):
        cache = CredentialCache(auth_mount)
        self._write_cred(auth_mount, "abc123", {
            "strategy": "bearer",
            "credential": "my-token",
        })
        assert cache.get_access_token("abc123") == "my-token"

    def test_missing_file_returns_none(self, auth_mount):
        cache = CredentialCache(auth_mount)
        assert cache.get_access_token("nonexistent") is None

    def test_cache_hit_skips_file_read(self, auth_mount):
        cache = CredentialCache(auth_mount)
        self._write_cred(auth_mount, "abc123", {
            "strategy": "bearer",
            "credential": "my-token",
        })

        # First call loads from file
        assert cache.get_access_token("abc123") == "my-token"

        # Delete file — cache should still return the token
        import os
        os.remove(f"{auth_mount}/abc123.json")
        assert cache.get_access_token("abc123") == "my-token"

    def test_cache_expires_after_ttl(self, auth_mount, monkeypatch):
        cache = CredentialCache(auth_mount)
        self._write_cred(auth_mount, "abc123", {
            "strategy": "bearer",
            "credential": "my-token",
        })

        # Load into cache
        assert cache.get_access_token("abc123") == "my-token"

        # Delete file and advance time past TTL
        import os
        os.remove(f"{auth_mount}/abc123.json")

        # Monkey-patch time.monotonic to simulate TTL expiry
        original = time.monotonic
        monkeypatch.setattr(time, "monotonic", lambda: original() + CACHE_TTL + 1)

        # Now cache miss, file gone → None
        assert cache.get_access_token("abc123") is None

    def test_revoked_file_detected_after_ttl(self, auth_mount, monkeypatch):
        cache = CredentialCache(auth_mount)
        self._write_cred(auth_mount, "abc123", {
            "strategy": "bearer",
            "credential": "my-token",
        })
        cache.get_access_token("abc123")

        # Simulate revocation
        import os
        os.remove(f"{auth_mount}/abc123.json")

        original = time.monotonic
        monkeypatch.setattr(time, "monotonic", lambda: original() + CACHE_TTL + 1)

        assert cache.get_access_token("abc123") is None

    def test_malformed_credential_raises(self, auth_mount):
        cache = CredentialCache(auth_mount)
        self._write_cred(auth_mount, "abc123", {
            "strategy": "bearer",
            # missing "credential" field
        })
        with pytest.raises(ValueError, match="missing 'credential' field"):
            cache.get_access_token("abc123")

    def test_unknown_strategy_raises(self, auth_mount):
        cache = CredentialCache(auth_mount)
        self._write_cred(auth_mount, "abc123", {
            "strategy": "nonexistent",
        })
        with pytest.raises(ValueError, match="Unknown credential strategy"):
            cache.get_access_token("abc123")


class TestRevokeBeforeCheck:
    @pytest.fixture
    def auth_mount(self, tmp_path):
        return str(tmp_path)

    def _write_cred(self, auth_mount, email_hash, data):
        path = f"{auth_mount}/{email_hash}.json"
        with open(path, "w") as f:
            json.dump(data, f)

    def test_no_revoke_before_allows_token(self, auth_mount):
        cache = CredentialCache(auth_mount)
        self._write_cred(auth_mount, "abc", {"strategy": "bearer", "credential": "x"})
        assert cache.check_revoke_before("abc", int(time.time())) is False

    def test_iat_before_cutoff_rejects(self, auth_mount):
        cache = CredentialCache(auth_mount)
        self._write_cred(auth_mount, "abc", {
            "strategy": "bearer",
            "credential": "x",
            "revoke_before": "2026-03-15T14:30:00Z",
        })
        # iat = March 10 → before cutoff
        iat = 1773408000  # ~2026-03-10
        assert cache.check_revoke_before("abc", iat) is True

    def test_iat_after_cutoff_allows(self, auth_mount):
        cache = CredentialCache(auth_mount)
        self._write_cred(auth_mount, "abc", {
            "strategy": "bearer",
            "credential": "x",
            "revoke_before": "2026-03-15T14:30:00Z",
        })
        # iat = March 20 → after cutoff
        iat = 1774272000  # ~2026-03-20
        assert cache.check_revoke_before("abc", iat) is False

    def test_missing_file_does_not_reject(self, auth_mount):
        cache = CredentialCache(auth_mount)
        assert cache.check_revoke_before("nonexistent", int(time.time())) is False
