"""Public pricing endpoints — quote calculator and rate-card listing."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.core.pricing import (
    BELT_WIDTHS,
    EDGE_APPLIANCE_KRW,
    EDGE_CARE_TIERS,
    LineSpec,
    build_quote,
    to_usd,
)
from app.schemas import (
    PricingCareBreakdown,
    PricingLineBreakdown,
    PricingMoney,
    PricingQuoteRequest,
    PricingQuoteResponse,
)

router = APIRouter(prefix="/v1/pricing", tags=["pricing"])


def _money(krw: float) -> PricingMoney:
    return PricingMoney(krw=int(round(krw)), usd=to_usd(krw))


def _normalize_tier(tier_id: str) -> str:
    """``pilot`` is the legacy alias for ``basic``."""
    return "basic" if tier_id == "pilot" else tier_id


@router.get("/catalog")
async def get_catalog() -> dict:
    """Public rate card — used by the marketing site."""
    care_tiers = [
        {
            "id": tier.id,
            "label": tier.label,
            "monthly_krw": tier.monthly_krw,
            "monthly_usd": to_usd(tier.monthly_krw),
            "included_lines": tier.included_lines,
            "included_inspections_per_month": tier.included_inspections_per_month,
            "overage_krw_per_inspection": tier.overage_krw_per_inspection,
            "extra_line_monthly_krw": tier.extra_line_monthly_krw,
        }
        for tier in EDGE_CARE_TIERS
    ]
    return {
        "belt_widths": [
            {
                "mm": bw.mm,
                "label": bw.label,
                "krw_per_meter": bw.krw_per_meter,
                "usd_per_meter": to_usd(bw.krw_per_meter),
            }
            for bw in BELT_WIDTHS
        ],
        "edge": {
            "krw": EDGE_APPLIANCE_KRW,
            "usd": to_usd(EDGE_APPLIANCE_KRW),
            "bundled_software": True,
            "note": (
                "On-device software (calibration UI, drift dashboard, OPC-UA "
                "bridge) is pre-installed on the integrated touch display. "
                "No separate desktop-app purchase."
            ),
        },
        "care_tiers": care_tiers,
        # Back-compat for v0 clients that still read ``cloud_tiers``.
        "cloud_tiers": care_tiers,
    }


@router.post("/quote", response_model=PricingQuoteResponse)
async def post_quote(payload: PricingQuoteRequest) -> PricingQuoteResponse:
    """Compute a one-time + recurring quote for a customer configuration."""
    try:
        quote = build_quote(
            [
                LineSpec(
                    belt_width_mm=spec.belt_width_mm,
                    belt_length_m=spec.belt_length_m,
                    monthly_inspections=spec.monthly_inspections,
                    spare_meshes=spec.spare_meshes,
                )
                for spec in payload.lines
            ],
            care_tier_id=_normalize_tier(payload.care_tier),
            monthly_inspections_override=payload.monthly_inspections_override,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc

    lines = [
        PricingLineBreakdown(
            belt_width_mm=line.belt_width.mm,
            belt_width_label=line.belt_width.label,
            belt_length_m=line.belt_length_m,
            mesh=_money(line.mesh_krw),
            edge=_money(line.edge_krw),
            spare_mesh=_money(line.spare_mesh_krw),
            total=_money(line.total_krw),
        )
        for line in quote.lines
    ]
    care = PricingCareBreakdown(
        tier_id=quote.care.tier.id,
        tier_label=quote.care.tier.label,
        base=_money(quote.care.base_monthly_krw),
        extra_lines=quote.care.extra_lines,
        extra_lines_total=_money(quote.care.extra_lines_monthly_krw),
        overage_inspections=quote.care.overage_inspections,
        overage_total=_money(quote.care.overage_monthly_krw),
        total_monthly=_money(quote.care.total_monthly_krw),
    )
    return PricingQuoteResponse(
        lines=lines,
        care=care,
        one_time_total=_money(quote.one_time_total_krw),
        monthly_total=_money(quote.monthly_total_krw),
        annual_total=_money(quote.annual_total_krw),
    )
