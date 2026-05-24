"""Pricing tables and the ``/v1/pricing/quote`` calculator.

The numbers here are the **single source of truth** for the marketing site
and the API. If you change a price on one side, change it here. The
frontend pricing section in ``web/index.html`` mirrors this table verbatim.

All amounts are quoted in **KRW**, with USD derived at quote time via the
configured ``CONET_PRICING_USD_PER_KRW`` rate. Prices are list prices
before negotiated volume discounts.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import settings

# ── meta ─────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class BeltWidth:
    """A standard belt-width SKU for the Tactile Mesh roll."""

    mm: int
    krw_per_meter: int
    label: str


@dataclass(frozen=True)
class CloudTier:
    """A Tactile Cloud SaaS subscription tier."""

    id: str
    label: str
    monthly_krw: int
    included_lines: int
    included_inspections_per_month: int
    overage_krw_per_inspection: float
    extra_line_monthly_krw: int


# ── catalogs ─────────────────────────────────────────────────────────


BELT_WIDTHS: list[BeltWidth] = [
    BeltWidth(mm=200, krw_per_meter=48_000, label="200 mm"),
    BeltWidth(mm=350, krw_per_meter=72_000, label="350 mm"),
    BeltWidth(mm=500, krw_per_meter=98_000, label="500 mm"),
    BeltWidth(mm=750, krw_per_meter=135_000, label="750 mm"),
    BeltWidth(mm=1_200, krw_per_meter=205_000, label="1200 mm (custom)"),
]


EDGE_APPLIANCE_KRW = 1_690_000
"""Tactile Edge appliance — one-time price per line."""

EDGE_SPARE_BOARD_KRW = 320_000
"""Spare scanner board (optional)."""

CLOUD_TIERS: list[CloudTier] = [
    CloudTier(
        id="pilot",
        label="Pilot",
        monthly_krw=1_290_000,
        included_lines=1,
        included_inspections_per_month=2_000_000,
        overage_krw_per_inspection=0.04,
        extra_line_monthly_krw=890_000,
    ),
    CloudTier(
        id="production",
        label="Production",
        monthly_krw=3_900_000,
        included_lines=4,
        included_inspections_per_month=10_000_000,
        overage_krw_per_inspection=0.025,
        extra_line_monthly_krw=720_000,
    ),
    CloudTier(
        id="fleet",
        label="Fleet",
        monthly_krw=9_900_000,
        included_lines=16,
        included_inspections_per_month=40_000_000,
        overage_krw_per_inspection=0.012,
        extra_line_monthly_krw=550_000,
    ),
]


# ── helpers ──────────────────────────────────────────────────────────


def to_usd(krw: float) -> float:
    return round(krw * settings.pricing_usd_per_krw, 2)


def find_belt_width(mm: int) -> BeltWidth:
    closest = min(BELT_WIDTHS, key=lambda b: abs(b.mm - mm))
    return closest


def find_cloud_tier(tier_id: str) -> CloudTier:
    for tier in CLOUD_TIERS:
        if tier.id == tier_id:
            return tier
    raise ValueError(f"unknown cloud tier: {tier_id!r}")


# ── quote calculator ─────────────────────────────────────────────────


@dataclass(frozen=True)
class LineSpec:
    """A single line in a quote request."""

    belt_width_mm: int
    belt_length_m: float
    monthly_inspections: int = 0
    spare_meshes: int = 0


@dataclass(frozen=True)
class QuoteLineBreakdown:
    """The cost breakdown for a single line."""

    belt_width: BeltWidth
    belt_length_m: float
    mesh_krw: int
    edge_krw: int
    spare_mesh_krw: int
    total_krw: int


@dataclass(frozen=True)
class QuoteCloudBreakdown:
    tier: CloudTier
    base_monthly_krw: int
    extra_lines: int
    extra_lines_monthly_krw: int
    overage_inspections: int
    overage_monthly_krw: int
    total_monthly_krw: int


@dataclass(frozen=True)
class Quote:
    lines: list[QuoteLineBreakdown]
    cloud: QuoteCloudBreakdown
    one_time_total_krw: int
    monthly_total_krw: int
    annual_total_krw: int


def build_quote(
    line_specs: list[LineSpec],
    cloud_tier_id: str = "production",
    monthly_inspections_override: int | None = None,
) -> Quote:
    """Compute the full quote for a customer-shaped configuration."""
    if not line_specs:
        raise ValueError("at least one line specification is required")
    if any(spec.belt_length_m <= 0 for spec in line_specs):
        raise ValueError("belt_length_m must be positive")
    if any(spec.belt_length_m > 100 for spec in line_specs):
        raise ValueError("belt_length_m capped at 100 m per line — split the order")

    line_breakdowns: list[QuoteLineBreakdown] = []
    total_inspections = 0
    for spec in line_specs:
        bw = find_belt_width(spec.belt_width_mm)
        mesh_meters = max(spec.belt_length_m, 0.5)
        mesh_krw = round(bw.krw_per_meter * mesh_meters)
        spare_mesh_krw = round(bw.krw_per_meter * mesh_meters * spec.spare_meshes)
        edge_krw = EDGE_APPLIANCE_KRW

        total_krw = mesh_krw + edge_krw + spare_mesh_krw
        line_breakdowns.append(
            QuoteLineBreakdown(
                belt_width=bw,
                belt_length_m=mesh_meters,
                mesh_krw=mesh_krw,
                edge_krw=edge_krw,
                spare_mesh_krw=spare_mesh_krw,
                total_krw=total_krw,
            )
        )
        total_inspections += spec.monthly_inspections

    if monthly_inspections_override is not None:
        total_inspections = monthly_inspections_override

    tier = find_cloud_tier(cloud_tier_id)
    n_lines = len(line_specs)
    extra_lines = max(0, n_lines - tier.included_lines)
    extra_lines_krw = extra_lines * tier.extra_line_monthly_krw

    overage = max(0, total_inspections - tier.included_inspections_per_month)
    overage_krw = round(overage * tier.overage_krw_per_inspection)

    cloud_total = tier.monthly_krw + extra_lines_krw + overage_krw
    cloud = QuoteCloudBreakdown(
        tier=tier,
        base_monthly_krw=tier.monthly_krw,
        extra_lines=extra_lines,
        extra_lines_monthly_krw=extra_lines_krw,
        overage_inspections=overage,
        overage_monthly_krw=overage_krw,
        total_monthly_krw=cloud_total,
    )

    one_time = sum(line.total_krw for line in line_breakdowns)
    annual = cloud_total * 12
    return Quote(
        lines=line_breakdowns,
        cloud=cloud,
        one_time_total_krw=one_time,
        monthly_total_krw=cloud_total,
        annual_total_krw=annual,
    )
