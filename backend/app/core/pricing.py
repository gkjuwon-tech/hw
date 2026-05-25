"""Pricing tables and the ``/v1/pricing/quote`` calculator.

The numbers here are the **single source of truth** for the marketing site
and the API. If you change a price on one side, change it here. The
frontend pricing section in ``web/index.html`` mirrors this table verbatim.

All amounts are quoted in **KRW**, with USD derived at quote time via the
configured ``CONET_PRICING_USD_PER_KRW`` rate. Prices are list prices
before negotiated volume discounts.

Pricing model
~~~~~~~~~~~~~

Tactile Edge ships as a single appliance with the on-device software
(calibration UI, drift dashboard, OPC-UA bridge) **pre-installed on the
integrated touch display** — there is no separate "desktop app" purchase.
The list price reflects the bundled software.

The recurring component is **Edge Care**, a maintenance plan that keeps the
on-device software updated, syncs fleet baselines from Tactile Cloud, and
ships replacement mesh rolls on schedule. It is not framed as a software
subscription because the software is already paid for with the appliance —
Edge Care is what keeps the *fleet* learning.
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
class EdgeCareTier:
    """An Edge Care maintenance tier.

    The shape mirrors the legacy ``CloudTier`` so the quote-calculator math
    stays identical — only the names and copy change. We keep
    ``included_inspections_per_month`` and ``overage_krw_per_inspection``
    because Tactile Cloud still bills inference at the platform level;
    they are surfaced to the customer as "included fleet sync volume" and
    "fleet-sync overage".
    """

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


EDGE_APPLIANCE_KRW = 1_990_000
"""Tactile Edge appliance — one-time price per line.

Includes the Jetson Orin Nano 8 GB compute module, the Conet Scanner PCB,
the integrated 7" capacitive touch display, the IP54 cabinet enclosure,
**and the pre-installed on-device software**. There is no separate
desktop-app purchase or activation fee.
"""

EDGE_SPARE_BOARD_KRW = 320_000
"""Spare scanner board (optional)."""

EDGE_CARE_TIERS: list[EdgeCareTier] = [
    EdgeCareTier(
        id="basic",
        label="Edge Care — Basic",
        monthly_krw=1_290_000,
        included_lines=1,
        included_inspections_per_month=2_000_000,
        overage_krw_per_inspection=0.04,
        extra_line_monthly_krw=890_000,
    ),
    EdgeCareTier(
        id="production",
        label="Edge Care — Production",
        monthly_krw=3_900_000,
        included_lines=4,
        included_inspections_per_month=10_000_000,
        overage_krw_per_inspection=0.025,
        extra_line_monthly_krw=720_000,
    ),
    EdgeCareTier(
        id="fleet",
        label="Edge Care — Fleet",
        monthly_krw=9_900_000,
        included_lines=16,
        included_inspections_per_month=40_000_000,
        overage_krw_per_inspection=0.012,
        extra_line_monthly_krw=550_000,
    ),
]

# Back-compat alias for callers that still import the old name.
CLOUD_TIERS = EDGE_CARE_TIERS


# ── helpers ──────────────────────────────────────────────────────────


def to_usd(krw: float) -> float:
    return round(krw * settings.pricing_usd_per_krw, 2)


def find_belt_width(mm: int) -> BeltWidth:
    closest = min(BELT_WIDTHS, key=lambda b: abs(b.mm - mm))
    return closest


def find_edge_care_tier(tier_id: str) -> EdgeCareTier:
    for tier in EDGE_CARE_TIERS:
        if tier.id == tier_id:
            return tier
    raise ValueError(f"unknown edge care tier: {tier_id!r}")


# Back-compat alias.
find_cloud_tier = find_edge_care_tier


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
class QuoteEdgeCareBreakdown:
    tier: EdgeCareTier
    base_monthly_krw: int
    extra_lines: int
    extra_lines_monthly_krw: int
    overage_inspections: int
    overage_monthly_krw: int
    total_monthly_krw: int


# Back-compat alias.
QuoteCloudBreakdown = QuoteEdgeCareBreakdown


@dataclass(frozen=True)
class Quote:
    lines: list[QuoteLineBreakdown]
    care: QuoteEdgeCareBreakdown
    one_time_total_krw: int
    monthly_total_krw: int
    annual_total_krw: int

    @property
    def cloud(self) -> QuoteEdgeCareBreakdown:
        """Back-compat alias for the legacy ``quote.cloud`` accessor."""
        return self.care


def build_quote(
    line_specs: list[LineSpec],
    care_tier_id: str = "production",
    monthly_inspections_override: int | None = None,
    *,
    cloud_tier_id: str | None = None,
) -> Quote:
    """Compute the full quote for a customer-shaped configuration.

    ``care_tier_id`` is the preferred name; ``cloud_tier_id`` is accepted
    as a back-compat keyword for the v0 callers that still use the old
    pricing vocabulary.
    """
    if cloud_tier_id is not None:
        care_tier_id = cloud_tier_id
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

    tier = find_edge_care_tier(care_tier_id)
    n_lines = len(line_specs)
    extra_lines = max(0, n_lines - tier.included_lines)
    extra_lines_krw = extra_lines * tier.extra_line_monthly_krw

    overage = max(0, total_inspections - tier.included_inspections_per_month)
    overage_krw = round(overage * tier.overage_krw_per_inspection)

    care_total = tier.monthly_krw + extra_lines_krw + overage_krw
    care = QuoteEdgeCareBreakdown(
        tier=tier,
        base_monthly_krw=tier.monthly_krw,
        extra_lines=extra_lines,
        extra_lines_monthly_krw=extra_lines_krw,
        overage_inspections=overage,
        overage_monthly_krw=overage_krw,
        total_monthly_krw=care_total,
    )

    one_time = sum(line.total_krw for line in line_breakdowns)
    annual = care_total * 12
    return Quote(
        lines=line_breakdowns,
        care=care,
        one_time_total_krw=one_time,
        monthly_total_krw=care_total,
        annual_total_krw=annual,
    )
