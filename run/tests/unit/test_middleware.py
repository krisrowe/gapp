"""Tests for auth middleware — JWT validation, token extraction, header rewrite."""

import hashlib
import json
import time

import jwt
import pytest

from gapp_run.auth.middleware import AuthMiddleware, _extract_token, _rewrite_auth_header

SIGNING_KEY = "test-secret-key"


def _make_jwt(sub="user@example.com", exp_offset=3600, **extra):
    """Create a signed JWT for testing."""
    payload = {
        "sub": sub,
        "iat": int(time.time()),
        "exp": int(time.time()) + exp_offset,
        **extra,
    }
    return jwt.encode(payload, SIGNING_KEY, algorithm="HS256")


def _make_scope(*, token=None, query_token=None, path="/mcp"):
    """Build a minimal ASGI HTTP scope."""
    headers = []
    if token:
        headers.append((b"authorization", f"Bearer {token}".encode()))
    query_string = f"token={query_token}" if query_token else ""
    return {
        "type": "http",
        "path": path,
        "headers": headers,
        "query_string": query_string.encode(),
    }


class TestTokenExtraction:
    def test_from_authorization_header(self):
        scope = _make_scope(token="my-jwt")
        assert _extract_token(scope) == "my-jwt"

    def test_from_query_param(self):
        scope = _make_scope(query_token="my-jwt")
        assert _extract_token(scope) == "my-jwt"

    def test_header_takes_precedence(self):
        scope = _make_scope(token="header-jwt", query_token="query-jwt")
        assert _extract_token(scope) == "header-jwt"

    def test_missing_returns_none(self):
        scope = _make_scope()
        assert _extract_token(scope) is None


class TestHeaderRewrite:
    def test_replaces_existing_header(self):
        headers = [(b"authorization", b"Bearer old"), (b"host", b"example.com")]
        result = _rewrite_auth_header(headers, "new-token")
        auth = dict(result)[b"authorization"]
        assert auth == b"Bearer new-token"

    def test_adds_header_if_missing(self):
        headers = [(b"host", b"example.com")]
        result = _rewrite_auth_header(headers, "new-token")
        auth = dict(result)[b"authorization"]
        assert auth == b"Bearer new-token"

    def test_preserves_other_headers(self):
        headers = [(b"host", b"example.com"), (b"authorization", b"Bearer old")]
        result = _rewrite_auth_header(headers, "new-token")
        assert dict(result)[b"host"] == b"example.com"


class TestAuthMiddleware:
    """Integration tests for the full middleware chain using a temp auth mount."""

    @pytest.fixture
    def auth_mount(self, tmp_path):
        return str(tmp_path)

    @pytest.fixture
    def write_credential(self, auth_mount):
        def _write(email, credential_data):
            email_hash = hashlib.sha256(email.encode()).hexdigest()
            path = f"{auth_mount}/{email_hash}.json"
            with open(path, "w") as f:
                json.dump(credential_data, f)
            return email_hash
        return _write

    def _make_middleware(self, auth_mount):
        """Create middleware wrapping a no-op ASGI app that records calls."""
        calls = []

        async def inner_app(scope, receive, send):
            calls.append(scope)
            body = b'{"ok": true}'
            await send({
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"content-type", b"application/json")],
            })
            await send({"type": "http.response.body", "body": body})

        mw = AuthMiddleware(inner_app, signing_key=SIGNING_KEY, auth_mount=auth_mount)
        return mw, calls

    async def _call(self, mw, scope):
        """Call middleware and capture the response."""
        responses = []

        async def receive():
            return {"type": "http.request", "body": b""}

        async def send(msg):
            responses.append(msg)

        await mw(scope, receive, send)
        return responses

    @pytest.mark.asyncio
    async def test_valid_jwt_rewrites_header(self, auth_mount, write_credential):
        write_credential("user@example.com", {
            "strategy": "bearer",
            "credential": "upstream-token-123",
        })
        mw, calls = self._make_middleware(auth_mount)
        token = _make_jwt("user@example.com")
        scope = _make_scope(token=token)

        await self._call(mw, scope)

        assert len(calls) == 1
        forwarded_auth = dict(calls[0]["headers"])[b"authorization"]
        assert forwarded_auth == b"Bearer upstream-token-123"

    @pytest.mark.asyncio
    async def test_missing_token_returns_401(self, auth_mount):
        mw, calls = self._make_middleware(auth_mount)
        scope = _make_scope()

        responses = await self._call(mw, scope)

        assert responses[0]["status"] == 401
        assert len(calls) == 0

    @pytest.mark.asyncio
    async def test_invalid_jwt_returns_403(self, auth_mount):
        mw, calls = self._make_middleware(auth_mount)
        scope = _make_scope(token="not-a-real-jwt")

        responses = await self._call(mw, scope)

        assert responses[0]["status"] == 403
        assert len(calls) == 0

    @pytest.mark.asyncio
    async def test_expired_jwt_returns_401(self, auth_mount):
        mw, calls = self._make_middleware(auth_mount)
        token = _make_jwt(exp_offset=-10)  # already expired
        scope = _make_scope(token=token)

        responses = await self._call(mw, scope)

        assert responses[0]["status"] == 401
        assert len(calls) == 0

    @pytest.mark.asyncio
    async def test_missing_credential_file_returns_403(self, auth_mount):
        mw, calls = self._make_middleware(auth_mount)
        token = _make_jwt("nobody@example.com")
        scope = _make_scope(token=token)

        responses = await self._call(mw, scope)

        assert responses[0]["status"] == 403
        assert len(calls) == 0

    @pytest.mark.asyncio
    async def test_query_param_token_works(self, auth_mount, write_credential):
        write_credential("user@example.com", {
            "strategy": "bearer",
            "credential": "upstream-token",
        })
        mw, calls = self._make_middleware(auth_mount)
        token = _make_jwt("user@example.com")
        scope = _make_scope(query_token=token)

        await self._call(mw, scope)

        assert len(calls) == 1

    @pytest.mark.asyncio
    async def test_health_endpoint_bypasses_auth(self, auth_mount):
        mw, calls = self._make_middleware(auth_mount)
        scope = _make_scope(path="/health")

        responses = await self._call(mw, scope)

        # Health goes to inner app (no auth required)
        assert len(calls) == 1

    @pytest.mark.asyncio
    async def test_lifespan_passes_through(self, auth_mount):
        mw, calls = self._make_middleware(auth_mount)
        scope = {"type": "lifespan"}

        await self._call(mw, scope)

        assert len(calls) == 1
        assert calls[0]["type"] == "lifespan"
