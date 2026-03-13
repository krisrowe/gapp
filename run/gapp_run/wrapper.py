"""gapp_run wrapper — ASGI entry point for deployed solutions.

Dynamically imports the solution's ASGI app, wraps it with auth
middleware, and serves it with a health endpoint.

Uvicorn entry point: gapp_run.wrapper:app

Environment variables:
    GAPP_APP: Solution's ASGI app (e.g., "monarch.mcp.server:mcp_app")
    GAPP_SIGNING_KEY: JWT signing key (from Secret Manager)
    GAPP_AUTH_MOUNT: Path to GCS FUSE mount (default: /mnt/auth)
"""

import importlib
import json
import os

from gapp_run.auth.middleware import AuthMiddleware


def _import_app(app_path: str):
    """Dynamically import the solution's ASGI app."""
    module_path, attr = app_path.rsplit(":", 1)
    module = importlib.import_module(module_path)
    return getattr(module, attr)


def _build_app():
    """Build the wrapped ASGI application."""
    app_path = os.environ.get("GAPP_APP")
    signing_key = os.environ.get("GAPP_SIGNING_KEY")
    auth_mount = os.environ.get("GAPP_AUTH_MOUNT", "/mnt/auth")

    if not app_path:
        raise RuntimeError("GAPP_APP environment variable is required")
    if not signing_key:
        raise RuntimeError("GAPP_SIGNING_KEY environment variable is required")

    inner_app = _import_app(app_path)

    # Wrap with health endpoint, then auth
    with_health = _HealthMiddleware(inner_app)
    return AuthMiddleware(with_health, signing_key=signing_key, auth_mount=auth_mount)


class _HealthMiddleware:
    """Serves /health before the request reaches the inner app."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope.get("path") == "/health":
            body = json.dumps({"status": "ok"}).encode()
            await send({
                "type": "http.response.start",
                "status": 200,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                ],
            })
            await send({
                "type": "http.response.body",
                "body": body,
            })
            return
        await self.app(scope, receive, send)


app = _build_app()
