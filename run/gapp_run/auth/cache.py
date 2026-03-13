"""Two-layer credential cache: in-memory (5-min TTL) + GCS FUSE files."""

import json
import time
from pathlib import Path

from gapp_run.auth.strategies import resolve_strategy

CACHE_TTL = 300  # 5 minutes


class CredentialCache:
    """Per-instance credential cache with FUSE-backed persistence."""

    def __init__(self, auth_mount: str):
        self._auth_mount = auth_mount
        # email_hash → (access_token, strategy_state, loaded_at)
        self._cache: dict[str, tuple[str, object, float]] = {}

    def get_access_token(self, email_hash: str) -> str | None:
        """Resolve a valid upstream access token for the given user.

        Returns None if the credential file doesn't exist (user revoked).
        Raises ValueError if the credential is malformed.
        """
        now = time.monotonic()

        # Layer 1: in-memory cache
        if email_hash in self._cache:
            token, state, loaded_at = self._cache[email_hash]
            if now - loaded_at < CACHE_TTL:
                # For google_oauth2, the state is a Credentials object —
                # check if the access token is still valid
                if state and hasattr(state, "valid") and not state.valid:
                    return self._refresh_oauth2(email_hash, state, now)
                return token

        # Layer 2: read from FUSE
        return self._load_from_file(email_hash, now)

    def _load_from_file(self, email_hash: str, now: float) -> str | None:
        """Read credential file, execute strategy, cache result."""
        cred_path = Path(self._auth_mount) / f"{email_hash}.json"
        if not cred_path.exists():
            # Evict from cache if previously cached
            self._cache.pop(email_hash, None)
            return None

        credential = json.loads(cred_path.read_text())
        strategy_name = credential.get("strategy", "bearer")
        strategy = resolve_strategy(strategy_name)

        if strategy_name == "google_oauth2":
            return self._load_oauth2(email_hash, credential, str(cred_path), now)

        # Bearer and other simple strategies
        token = strategy(credential)
        self._cache[email_hash] = (token, None, now)
        return token

    def _load_oauth2(
        self, email_hash: str, credential: dict, cred_path: str, now: float,
    ) -> str:
        """Load Google OAuth2 credential, refresh if needed, cache the Credentials object."""
        from google.oauth2.credentials import Credentials
        from gapp_run.auth.strategies.google_oauth2 import get_access_token, _write_back

        creds = Credentials.from_authorized_user_info(credential)

        if not creds.valid:
            if not creds.refresh_token:
                raise ValueError("Credential missing refresh_token")
            from google.auth.transport.requests import Request
            creds.refresh(Request())
            _write_back(cred_path, credential, creds)

        self._cache[email_hash] = (creds.token, creds, now)
        return creds.token

    def _refresh_oauth2(
        self, email_hash: str, creds, now: float,
    ) -> str:
        """Refresh an expired cached Credentials object."""
        from google.auth.transport.requests import Request
        creds.refresh(Request())

        # Write back to FUSE for cross-instance reuse
        cred_path = Path(self._auth_mount) / f"{email_hash}.json"
        if cred_path.exists():
            credential = json.loads(cred_path.read_text())
            from gapp_run.auth.strategies.google_oauth2 import _write_back
            _write_back(str(cred_path), credential, creds)

        self._cache[email_hash] = (creds.token, creds, now)
        return creds.token

    def check_revoke_before(self, email_hash: str, iat: int) -> bool:
        """Check if a JWT's iat is before the revoke_before timestamp.

        Returns True if the token should be rejected.
        Reads from the cached credential file data.
        """
        cred_path = Path(self._auth_mount) / f"{email_hash}.json"
        if not cred_path.exists():
            return False

        credential = json.loads(cred_path.read_text())
        revoke_before = credential.get("revoke_before")
        if not revoke_before:
            return False

        from datetime import datetime, timezone
        cutoff = datetime.fromisoformat(revoke_before)
        if cutoff.tzinfo is None:
            cutoff = cutoff.replace(tzinfo=timezone.utc)
        token_time = datetime.fromtimestamp(iat, tz=timezone.utc)
        return token_time < cutoff
