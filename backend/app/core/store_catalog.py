"""Storefront SKU catalog.

The marketing site sells two things directly:

1.  **Tactile Edge** — a one-time hardware purchase. The inference
    appliance ships with the on-device software (calibration UI, drift
    dashboard, OPC-UA bridge) **pre-installed on the integrated touch
    display**. There is no separate desktop-app purchase. Shipped from
    Seoul; customs and freight are calculated at checkout.
2.  **Edge Care — Basic** — a recurring monthly maintenance plan. Keeps
    the on-device software updated, syncs fleet baselines from Tactile
    Cloud, and ships replacement mesh rolls on schedule. First month is
    free; the plan activates automatically after the hardware purchase
    succeeds.

The values here are the **single source of truth** for the storefront API
and the marketing site. The marketing pages mirror these numbers and read
the catalog at runtime via ``/v1/store/catalog`` so the two never drift.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HardwareSku:
    """A one-time-purchase hardware SKU."""

    id: str
    label: str
    description: str
    unit_amount_usd: int
    """Integer USD amount, i.e. ``1290`` means $1,290.00."""

    image_path: str
    """Path under ``web/assets/`` for the product card image."""


@dataclass(frozen=True)
class SoftwarePlan:
    """A recurring maintenance plan.

    Historically called a "software plan" — kept as the class name for
    schema stability. Customer-visible labels now use "Edge Care" since
    the on-device software is bundled with the appliance and what the
    customer pays monthly for is the *maintenance* (updates, fleet sync,
    consumable refills), not the software itself.
    """

    id: str
    label: str
    description: str
    monthly_amount_usd: int
    trial_days: int


# ── hardware ───────────────────────────────────────────────────────


TACTILE_EDGE = HardwareSku(
    id="tactile_edge",
    label="Tactile Edge",
    description=(
        "An inference appliance for the line cabinet with an integrated "
        "7\" capacitive touch display. The on-device software "
        "(calibration UI, drift dashboard, OPC-UA bridge) is pre-installed "
        "and runs as a Chromium kiosk on the built-in display — no "
        "operator PC required. Ships with a 350 mm starter Tactile Mesh "
        "roll, rotary cutter, termination clips, and an install jig. "
        "From Seoul, three weeks, customs at checkout."
    ),
    unit_amount_usd=1_490,
    image_path="assets/hero-factory.jpg",
)


HARDWARE_SKUS: dict[str, HardwareSku] = {
    TACTILE_EDGE.id: TACTILE_EDGE,
}


# ── recurring maintenance plan ─────────────────────────────────────


EDGE_CARE_BASIC = SoftwarePlan(
    id="edge_care_basic",
    label="Edge Care — Basic",
    description=(
        "Per-line maintenance plan for the Tactile Edge appliance. "
        "Keeps the on-device software updated, syncs fleet baselines from "
        "Tactile Cloud for drift detection, delivers signed webhook "
        "events to your MES/SCADA, and ships replacement mesh rolls on "
        "schedule. First month free; cancel anytime from the on-device "
        "kiosk or via /v1/admin."
    ),
    monthly_amount_usd=49,
    trial_days=30,
)


# Legacy alias — the old plan id is kept so v0 checkout links don't 404.
# It points to the same row as the new ``edge_care_basic`` plan.
TACTILE_CLOUD_PILOT = EDGE_CARE_BASIC


SOFTWARE_PLANS: dict[str, SoftwarePlan] = {
    EDGE_CARE_BASIC.id: EDGE_CARE_BASIC,
}

# Legacy id → current plan, kept out of the catalog listing so the
# storefront doesn't show two cards for the same product.
_LEGACY_SOFTWARE_PLAN_IDS: dict[str, SoftwarePlan] = {
    "tactile_cloud_pilot": EDGE_CARE_BASIC,
}


def get_hardware_sku(sku_id: str) -> HardwareSku:
    """Look up a hardware SKU by id. Raises ``KeyError`` if unknown."""
    return HARDWARE_SKUS[sku_id]


def get_software_plan(plan_id: str) -> SoftwarePlan:
    """Look up a maintenance plan by id. Raises ``KeyError`` if unknown.

    Accepts legacy plan ids (``tactile_cloud_pilot``) so v0 checkout links
    stay valid; the canonical id is ``edge_care_basic``.
    """
    if plan_id in SOFTWARE_PLANS:
        return SOFTWARE_PLANS[plan_id]
    if plan_id in _LEGACY_SOFTWARE_PLAN_IDS:
        return _LEGACY_SOFTWARE_PLAN_IDS[plan_id]
    raise KeyError(plan_id)
