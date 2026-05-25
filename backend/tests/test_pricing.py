"""Pricing endpoint and quote calculator."""

from __future__ import annotations

from httpx import AsyncClient

from app.core.pricing import EDGE_APPLIANCE_KRW, LineSpec, build_quote


def test_quote_minimal_one_line() -> None:
    quote = build_quote(
        [LineSpec(belt_width_mm=500, belt_length_m=2.0, monthly_inspections=1_000)],
        care_tier_id="production",
    )
    # 2.0 m * 98,000 KRW/m = 196,000 KRW mesh
    assert quote.lines[0].mesh_krw == 196_000
    assert quote.lines[0].edge_krw == EDGE_APPLIANCE_KRW
    assert quote.lines[0].total_krw == 196_000 + EDGE_APPLIANCE_KRW
    assert quote.care.tier.id == "production"
    # Back-compat: the legacy ``quote.cloud`` accessor still works.
    assert quote.cloud.tier.id == "production"
    # No overage with 1k inspections vs 10M included.
    assert quote.care.overage_inspections == 0


def test_quote_overage_and_extra_lines() -> None:
    quote = build_quote(
        [
            LineSpec(belt_width_mm=350, belt_length_m=1.0)
            for _ in range(6)
        ],
        care_tier_id="production",
        monthly_inspections_override=20_000_000,  # 10M over
    )
    assert quote.care.extra_lines == 2  # 6 lines, 4 included
    assert quote.care.overage_inspections == 10_000_000
    # 10M * 0.025 KRW = 250,000 KRW
    assert quote.care.overage_monthly_krw == 250_000
    assert quote.care.total_monthly_krw == (
        3_900_000 + 2 * 720_000 + 250_000
    )


def test_quote_rejects_empty_or_oversize() -> None:
    import pytest

    with pytest.raises(ValueError):
        build_quote([], care_tier_id="basic")

    with pytest.raises(ValueError):
        build_quote(
            [LineSpec(belt_width_mm=500, belt_length_m=200)],
            care_tier_id="basic",
        )

    # ``pilot`` is still accepted as a legacy alias for ``basic``.
    quote = build_quote(
        [LineSpec(belt_width_mm=500, belt_length_m=2.0)],
        care_tier_id="basic",
        cloud_tier_id="basic",
    )
    assert quote.care.tier.id == "basic"


async def test_pricing_catalog_endpoint(client: AsyncClient) -> None:
    r = await client.get("/v1/pricing/catalog")
    assert r.status_code == 200
    body = r.json()
    assert any(b["mm"] == 500 for b in body["belt_widths"])
    assert any(t["id"] == "production" for t in body["care_tiers"])
    # Legacy clients still read the ``cloud_tiers`` alias.
    assert any(t["id"] == "production" for t in body["cloud_tiers"])
    assert body["edge"]["krw"] == EDGE_APPLIANCE_KRW
    assert body["edge"]["bundled_software"] is True


async def test_pricing_quote_endpoint(client: AsyncClient) -> None:
    r = await client.post(
        "/v1/pricing/quote",
        json={
            "lines": [
                {"belt_width_mm": 750, "belt_length_m": 3, "monthly_inspections": 0}
            ],
            "care_tier": "fleet",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["lines"][0]["belt_width_mm"] == 750
    assert body["care"]["tier_id"] == "fleet"
    assert body["monthly_total"]["krw"] == 9_900_000
    assert body["annual_total"]["krw"] == 9_900_000 * 12


async def test_pricing_quote_validation(client: AsyncClient) -> None:
    r = await client.post(
        "/v1/pricing/quote",
        json={"lines": [], "care_tier": "production"},
    )
    assert r.status_code == 422
