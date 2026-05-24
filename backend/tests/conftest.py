"""Shared fixtures.

Each test gets an isolated SQLite database and data directory, an isolated
ASGI client, and a freshly imported ``app`` package so settings changes are
picked up.
"""

from __future__ import annotations

import sys
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.fixture
def isolated_env(monkeypatch: pytest.MonkeyPatch) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="conet-test-"))
    monkeypatch.setenv("CONET_DATA_DIR", str(tmp))
    monkeypatch.setenv("CONET_DATABASE_URL", f"sqlite+aiosqlite:///{tmp / 'test.db'}")
    monkeypatch.setenv("CONET_LOG_JSON", "false")
    monkeypatch.setenv("CONET_RATE_LIMIT_ENABLED", "false")
    monkeypatch.setenv("CONET_METRICS_ENABLED", "true")
    # Force a fresh import of the app package so the new env is honored.
    for mod in [m for m in list(sys.modules) if m.startswith("app")]:
        del sys.modules[mod]
    return tmp


@pytest.fixture
async def client(isolated_env: Path) -> AsyncIterator[AsyncClient]:
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        async with app.router.lifespan_context(app):
            yield c


@pytest.fixture
async def authed_client(
    monkeypatch: pytest.MonkeyPatch,
) -> AsyncIterator[tuple[AsyncClient, str, str, str]]:
    """A client wired against an app with auth REQUIRED.

    Returns ``(client, admin_token, org_id, api_key)``.
    """
    tmp = Path(tempfile.mkdtemp(prefix="conet-test-auth-"))
    admin_token = "admin-test-token"  # noqa: S105 — test fixture
    monkeypatch.setenv("CONET_DATA_DIR", str(tmp))
    monkeypatch.setenv("CONET_DATABASE_URL", f"sqlite+aiosqlite:///{tmp / 'test.db'}")
    monkeypatch.setenv("CONET_LOG_JSON", "false")
    monkeypatch.setenv("CONET_RATE_LIMIT_ENABLED", "false")
    monkeypatch.setenv("CONET_AUTH_REQUIRED", "true")
    monkeypatch.setenv("CONET_BOOTSTRAP_ADMIN_TOKEN", admin_token)
    for mod in [m for m in list(sys.modules) if m.startswith("app")]:
        del sys.modules[mod]

    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        async with app.router.lifespan_context(app):
            # Bootstrap an org + key via the admin endpoints.
            r = await c.post(
                "/v1/admin/organizations",
                headers={"x-admin-token": admin_token},
                json={
                    "id": "org_test",
                    "name": "Test Org",
                    "contact_email": "test@conet.local",
                    "rate_limit_per_minute": 0,
                },
            )
            assert r.status_code == 201, r.text
            org_id = r.json()["id"]

            r = await c.post(
                "/v1/admin/api-keys",
                headers={"x-admin-token": admin_token},
                json={"org_id": org_id, "label": "test", "scope": "read_write"},
            )
            assert r.status_code == 201, r.text
            api_key = r.json()["raw"]

            yield c, admin_token, org_id, api_key
