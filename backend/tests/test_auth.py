"""Multi-tenant auth: missing key → 401, wrong key → 401, scoping → 404."""

from __future__ import annotations

from httpx import AsyncClient


async def test_missing_key_rejected(
    authed_client: tuple[AsyncClient, str, str, str],
) -> None:
    client, _admin, _org, _key = authed_client
    r = await client.get("/v1/lines")
    assert r.status_code == 401
    assert "bearer" in r.headers.get("www-authenticate", "").lower()


async def test_invalid_key_rejected(
    authed_client: tuple[AsyncClient, str, str, str],
) -> None:
    client, _admin, _org, _key = authed_client
    r = await client.get("/v1/lines", headers={"authorization": "Bearer not-a-real-key"})
    assert r.status_code == 401


async def test_valid_key_allows_listing(
    authed_client: tuple[AsyncClient, str, str, str],
) -> None:
    client, _admin, _org, key = authed_client
    r = await client.get("/v1/lines", headers={"authorization": f"Bearer {key}"})
    assert r.status_code == 200
    assert r.json() == []


async def test_admin_token_required(
    authed_client: tuple[AsyncClient, str, str, str],
) -> None:
    client, _admin, _org, _key = authed_client
    r = await client.post(
        "/v1/admin/organizations",
        json={"id": "should-not-exist", "name": "x"},
    )
    assert r.status_code == 401


async def test_cross_org_isolation(
    authed_client: tuple[AsyncClient, str, str, str],
) -> None:
    client, admin, _org, key_a = authed_client

    # Make a line on org A.
    r = await client.post(
        "/v1/lines",
        headers={"authorization": f"Bearer {key_a}"},
        json={"id": "line-a", "customer_tag": "a", "rows": 4, "cols": 4},
    )
    assert r.status_code == 201, r.text

    # Bootstrap a second org with its own key.
    r = await client.post(
        "/v1/admin/organizations",
        headers={"x-admin-token": admin},
        json={"id": "org_b", "name": "B", "contact_email": ""},
    )
    assert r.status_code == 201
    r = await client.post(
        "/v1/admin/api-keys",
        headers={"x-admin-token": admin},
        json={"org_id": "org_b", "label": "b"},
    )
    key_b = r.json()["raw"]

    # Org B must not see line A.
    r = await client.get(
        "/v1/lines/line-a",
        headers={"authorization": f"Bearer {key_b}"},
    )
    assert r.status_code == 404

    r = await client.get(
        "/v1/lines",
        headers={"authorization": f"Bearer {key_b}"},
    )
    assert r.json() == []


async def test_revoked_key_rejected(
    authed_client: tuple[AsyncClient, str, str, str],
) -> None:
    client, admin, _org, key = authed_client
    # Revoke by id (prefix).
    key_id = key[: len("ctk_live_") + 8]
    r = await client.post(
        f"/v1/admin/api-keys/{key_id}/revoke",
        headers={"x-admin-token": admin},
    )
    assert r.status_code == 200
    r = await client.get("/v1/lines", headers={"authorization": f"Bearer {key}"})
    assert r.status_code == 401


async def test_read_only_scope_blocks_writes(
    authed_client: tuple[AsyncClient, str, str, str],
) -> None:
    client, admin, org, _key = authed_client
    r = await client.post(
        "/v1/admin/api-keys",
        headers={"x-admin-token": admin},
        json={"org_id": org, "label": "ro", "scope": "read_only"},
    )
    ro_key = r.json()["raw"]
    r = await client.post(
        "/v1/lines",
        headers={"authorization": f"Bearer {ro_key}"},
        json={"id": "ro-line", "customer_tag": "", "rows": 4, "cols": 4},
    )
    assert r.status_code == 403
    # Read is fine.
    r = await client.get("/v1/lines", headers={"authorization": f"Bearer {ro_key}"})
    assert r.status_code == 200
