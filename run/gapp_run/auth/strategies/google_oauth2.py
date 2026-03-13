"""Google OAuth2 strategy — refresh access tokens from authorized_user credentials."""

import json
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials


def get_access_token(credential: dict, *, cred_path: str | None = None) -> str:
    """Produce a valid Google access token from an authorized_user credential.

    If the access token is expired, refreshes it using the refresh_token and
    writes the updated credential back to the file (FUSE syncs to GCS for
    cross-instance reuse).

    Args:
        credential: The credential dict from the JSON file.
        cred_path: Path to the credential file, for write-back after refresh.

    Returns:
        A valid access token string.
    """
    creds = Credentials.from_authorized_user_info(credential)

    if not creds.valid:
        if not creds.refresh_token:
            raise ValueError("Credential file missing refresh_token — cannot refresh")
        creds.refresh(Request())

        # Write back so other instances get the fresh access token
        if cred_path:
            _write_back(cred_path, credential, creds)

    return creds.token


def _write_back(cred_path: str, original: dict, creds: Credentials) -> None:
    """Persist the refreshed credential back to disk (FUSE → GCS)."""
    updated = {**original, "token": creds.token}
    if creds.expiry:
        updated["expiry"] = creds.expiry.isoformat()
    Path(cred_path).write_text(json.dumps(updated))
