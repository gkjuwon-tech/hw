"""Recipes — per-product saved inspection configs."""

from __future__ import annotations

import uuid

from httpx import AsyncClient


async def _make_line(client: AsyncClient) -> str:
    line_id = f"line-{uuid.uuid4().hex[:8]}"
    r = await client.post(
        "/v1/lines",
        json={"id": line_id, "customer_tag": "recipe-line", "rows": 8, "cols": 8},
    )
    assert r.status_code == 201
    return line_id


async def test_recipe_crud(client: AsyncClient) -> None:
    r = await client.post(
        "/v1/recipes",
        json={
            "name": "Bread loaf 500g",
            "product_sku": "BRD-500",
            "description": "Hot baked bread.",
            "threshold_score": 4.0,
            "threshold_hits": 12,
            "blob_min_area": 6,
            "trigger_mode": "encoder",
            "strobe_duty_pct": 60.0,
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    rid = body["id"]
    assert body["name"] == "Bread loaf 500g"
    assert body["threshold_score"] == 4.0
    assert body["trigger_mode"] == "encoder"

    r = await client.get("/v1/recipes")
    assert r.status_code == 200
    assert any(x["id"] == rid for x in r.json())

    r = await client.patch(
        f"/v1/recipes/{rid}",
        json={"threshold_score": 5.5, "blob_min_area": 8},
    )
    assert r.status_code == 200
    assert r.json()["threshold_score"] == 5.5
    assert r.json()["blob_min_area"] == 8

    r = await client.delete(f"/v1/recipes/{rid}")
    assert r.status_code == 204

    r = await client.get(f"/v1/recipes/{rid}")
    assert r.status_code == 404


async def test_load_recipe_into_line(client: AsyncClient) -> None:
    line_id = await _make_line(client)

    r = await client.post(
        "/v1/recipes",
        json={
            "name": "Pizza 10in",
            "threshold_score": 2.5,
            "threshold_hits": 6,
        },
    )
    rid = r.json()["id"]

    r = await client.post(
        f"/v1/lines/{line_id}/load_recipe",
        json={"recipe_id": rid},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["recipe_id"] == rid
    assert body["threshold_score"] == 2.5
    assert body["threshold_hits"] == 6

    # Confirm the line was actually updated.
    r = await client.get(f"/v1/lines/{line_id}")
    assert r.json()["threshold_score"] == 2.5
    assert r.json()["threshold_hits"] == 6


async def test_recipe_invalid_trigger_mode(client: AsyncClient) -> None:
    r = await client.post(
        "/v1/recipes",
        json={"name": "x", "trigger_mode": "not-a-mode"},
    )
    assert r.status_code == 422
