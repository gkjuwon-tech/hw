"""Storefront SKU catalog.

The marketing site sells two things directly:

1.  **Tactile Edge** — a one-time hardware purchase. A fanless inference
    appliance with the new Conet Scanner board, pre-flashed and
    provisioned. Shipped from Seoul; customs and freight are calculated
    at checkout.
2.  **Tactile Cloud — Pilot** — a recurring monthly subscription that is
    gated by a first-month free trial. Activated automatically after the
    hardware purchase succeeds.

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
    """A recurring software subscription plan."""

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
        "A fanless inference appliance for the line cabinet. Pre-flashed "
        "and provisioned to your Tactile Cloud workspace, ships with a 350 mm "
        "starter Tactile Mesh roll, rotary cutter, termination clips, and an "
        "install jig. From Seoul, three weeks, customs at checkout."
    ),
    unit_amount_usd=1_290,
    image_path="assets/hero-factory.jpg",
)


HARDWARE_SKUS: dict[str, HardwareSku] = {
    TACTILE_EDGE.id: TACTILE_EDGE,
}


# ── software subscription ──────────────────────────────────────────


TACTILE_CLOUD_PILOT = SoftwarePlan(
    id="tactile_cloud_pilot",
    label="Tactile Cloud — Pilot",
    description=(
        "Per-line SaaS for calibration, drift detection, dashboards, and "
        "webhook delivery. First month free; cancel anytime in the desktop "
        "app or via /v1/admin."
    ),
    monthly_amount_usd=49,
    trial_days=30,
)


SOFTWARE_PLANS: dict[str, SoftwarePlan] = {
    TACTILE_CLOUD_PILOT.id: TACTILE_CLOUD_PILOT,
}


def get_hardware_sku(sku_id: str) -> HardwareSku:
    """Look up a hardware SKU by id. Raises ``KeyError`` if unknown."""
    return HARDWARE_SKUS[sku_id]


def get_software_plan(plan_id: str) -> SoftwarePlan:
    """Look up a software plan by id. Raises ``KeyError`` if unknown."""
    return SOFTWARE_PLANS[plan_id]
