"""gapp user management — register, list, and revoke users via GCS credential files."""

import hashlib
import json
import secrets
import subprocess
from datetime import datetime, timezone

from gapp.sdk.context import resolve_solution


def _get_bucket_name(ctx: dict) -> str:
    """Derive the GCS bucket name for a solution."""
    return f"gapp-{ctx['name']}-{ctx['project_id']}"


def _require_context() -> dict:
    """Resolve solution context or raise."""
    ctx = resolve_solution()
    if not ctx:
        raise RuntimeError(
            "Not inside a gapp solution. Run 'gapp init' first, or cd into a solution repo."
        )
    if not ctx.get("project_id"):
        raise RuntimeError("No GCP project attached. Run 'gapp setup <project-id>' first.")
    return ctx


def _email_hash(email: str) -> str:
    """SHA-256 hash of email address."""
    return hashlib.sha256(email.lower().strip().encode()).hexdigest()


def _gcs_path(bucket: str, email_hash: str) -> str:
    """GCS path for a user's credential file."""
    return f"gs://{bucket}/auth/{email_hash}.json"


def _object_exists(gcs_path: str) -> bool:
    """Check if a GCS object exists."""
    result = subprocess.run(
        ["gcloud", "storage", "stat", gcs_path],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def register_user(
    email: str,
    credential: str,
    strategy: str = "bearer",
) -> dict:
    """Register a new user by writing a credential file to GCS.

    Generates a PAT, writes the credential file, and returns the PAT.
    Raises RuntimeError if the user already exists.
    """
    ctx = _require_context()
    bucket = _get_bucket_name(ctx)
    eh = _email_hash(email)
    gcs_path = _gcs_path(bucket, eh)

    if _object_exists(gcs_path):
        raise RuntimeError(f"User '{email}' already registered. Use 'gapp users update' to change credentials.")

    now = datetime.now(timezone.utc).isoformat()
    credential_data = {
        "strategy": strategy,
        "credential": credential,
        "sub": email,
        "created": now,
    }

    _write_credential(gcs_path, credential_data)

    return {
        "email": email,
        "email_hash": eh,
        "strategy": strategy,
        "created": now,
    }


def list_users(*, limit: int = 10, start_index: int = 0) -> dict:
    """List registered users by reading credential files from GCS.

    Returns dict with solution info and list of users.
    """
    ctx = _require_context()
    bucket = _get_bucket_name(ctx)
    prefix = f"gs://{bucket}/auth/"

    # List objects in auth/ prefix
    result = subprocess.run(
        ["gcloud", "storage", "ls", prefix],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        # No auth/ prefix yet — empty list
        return {"name": ctx["name"], "users": [], "total": 0}

    # Parse object paths
    paths = [line.strip() for line in result.stdout.strip().splitlines() if line.strip()]
    total = len(paths)

    # Apply pagination
    page = paths[start_index:start_index + limit]

    users = []
    for path in page:
        user_info = _read_credential_metadata(path)
        if user_info:
            users.append(user_info)

    return {
        "name": ctx["name"],
        "users": users,
        "total": total,
        "start_index": start_index,
        "limit": limit,
    }


def update_user(
    email: str,
    *,
    credential: str | None = None,
    revoke_before: str | None = None,
) -> dict:
    """Update a user's credential file in GCS.

    Can update the upstream credential, set revoke_before, or both.
    revoke_before is an ISO 8601 timestamp — all JWTs with iat before
    this time will be rejected.
    """
    ctx = _require_context()
    bucket = _get_bucket_name(ctx)
    eh = _email_hash(email)
    gcs_path = _gcs_path(bucket, eh)

    if not _object_exists(gcs_path):
        raise RuntimeError(f"User '{email}' not found.")

    # Read existing credential
    existing = _read_credential_full(gcs_path)
    if existing is None:
        raise RuntimeError(f"Failed to read credential for '{email}'.")

    updated = dict(existing)
    changes = []

    if credential is not None:
        updated["credential"] = credential
        changes.append("credential")

    if revoke_before is not None:
        updated["revoke_before"] = revoke_before
        changes.append("revoke_before")

    if not changes:
        raise RuntimeError("Nothing to update. Specify --credential or --revoke-before.")

    _write_credential(gcs_path, updated)

    return {
        "email": email,
        "email_hash": eh,
        "changes": changes,
    }


def revoke_user(email: str) -> dict:
    """Revoke a user by deleting their credential file from GCS."""
    ctx = _require_context()
    bucket = _get_bucket_name(ctx)
    eh = _email_hash(email)
    gcs_path = _gcs_path(bucket, eh)

    if not _object_exists(gcs_path):
        raise RuntimeError(f"User '{email}' not found.")

    result = subprocess.run(
        ["gcloud", "storage", "rm", gcs_path],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Failed to revoke user: {result.stderr.strip()}")

    return {"email": email, "email_hash": eh, "status": "revoked"}


def _write_credential(gcs_path: str, data: dict) -> None:
    """Write a credential JSON file to GCS via stdin."""
    payload = json.dumps(data)
    result = subprocess.run(
        ["gcloud", "storage", "cp", "-", gcs_path],
        input=payload,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"Failed to write credential: {result.stderr.strip()}")


def _read_credential_full(gcs_path: str) -> dict | None:
    """Read a credential file from GCS and return the full dict."""
    result = subprocess.run(
        ["gcloud", "storage", "cat", gcs_path],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return None


def _read_credential_metadata(gcs_path: str) -> dict | None:
    """Read a credential file from GCS and return safe metadata (no secrets)."""
    result = subprocess.run(
        ["gcloud", "storage", "cat", gcs_path],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None

    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None

    # Extract filename (email hash) from path
    filename = gcs_path.rstrip("/").rsplit("/", 1)[-1]
    email_hash = filename.replace(".json", "")

    return {
        "email_hash": email_hash,
        "sub": data.get("sub", ""),
        "strategy": data.get("strategy", ""),
        "created": data.get("created", ""),
    }
