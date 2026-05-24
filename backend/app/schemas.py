"""Pydantic schemas for the public API."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

# ── lines ────────────────────────────────────────────────────────────


class LineCreate(BaseModel):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_\-]+$")
    customer_tag: str = Field(default="", max_length=128)
    rows: int = Field(gt=0, le=512)
    cols: int = Field(gt=0, le=512)


class LineUpdate(BaseModel):
    customer_tag: str | None = Field(default=None, max_length=128)
    threshold_score: float | None = Field(default=None, ge=0.0, le=20.0)
    threshold_hits: int | None = Field(default=None, ge=0, le=10_000)


class LineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    org_id: str
    customer_tag: str
    rows: int
    cols: int
    status: str
    created_at: datetime
    calibrated_at: datetime | None = None
    n_samples: int
    drift: float
    drift_z: float
    threshold_score: float
    threshold_hits: int


# ── frames / calibration ─────────────────────────────────────────────


class FrameIn(BaseModel):
    """A single tactile frame.

    ``data`` is a row-major list of length ``rows * cols``. Values are 0..255
    (8-bit) but we accept floats so a host with calibrated raw counts can
    upsample.
    """

    data: list[float] = Field(min_length=1, max_length=512 * 512)


class CalibrateRequest(BaseModel):
    n_samples: int | None = Field(
        default=None,
        ge=1,
        le=64,
        description="Number of buffered samples to use (most recent). Default: all.",
    )


class CalibrateResponse(BaseModel):
    line_id: str
    n_samples: int
    rows: int
    cols: int
    mean_min: float
    mean_max: float


# ── inspection ───────────────────────────────────────────────────────


class InspectResponse(BaseModel):
    line_id: str
    score: float
    hits: int
    cell_score_max: float
    verdict: str
    drift_z: float = 0.0
    features: dict[str, float]
    heatmap: list[list[float]] | None = None


class EventOut(BaseModel):
    line_id: str
    score: float
    hits: int
    verdict: str
    created_at: datetime


# ── pricing ──────────────────────────────────────────────────────────


class PricingLineSpec(BaseModel):
    belt_width_mm: int = Field(ge=100, le=2_000)
    belt_length_m: float = Field(gt=0, le=100)
    monthly_inspections: int = Field(default=0, ge=0, le=10**9)
    spare_meshes: int = Field(default=0, ge=0, le=20)


class PricingQuoteRequest(BaseModel):
    lines: list[PricingLineSpec] = Field(min_length=1, max_length=64)
    cloud_tier: Literal["pilot", "production", "fleet"] = "production"
    monthly_inspections_override: int | None = Field(default=None, ge=0, le=10**12)


class PricingMoney(BaseModel):
    krw: int
    usd: float


class PricingLineBreakdown(BaseModel):
    belt_width_mm: int
    belt_width_label: str
    belt_length_m: float
    mesh: PricingMoney
    edge: PricingMoney
    spare_mesh: PricingMoney
    total: PricingMoney


class PricingCloudBreakdown(BaseModel):
    tier_id: str
    tier_label: str
    base: PricingMoney
    extra_lines: int
    extra_lines_total: PricingMoney
    overage_inspections: int
    overage_total: PricingMoney
    total_monthly: PricingMoney


class PricingQuoteResponse(BaseModel):
    lines: list[PricingLineBreakdown]
    cloud: PricingCloudBreakdown
    one_time_total: PricingMoney
    monthly_total: PricingMoney
    annual_total: PricingMoney


# ── webhooks ─────────────────────────────────────────────────────────


class WebhookCreate(BaseModel):
    url: HttpUrl
    events: list[str] = Field(
        default_factory=lambda: ["inspection.failed", "drift.alert"],
        max_length=16,
    )
    description: str = Field(default="", max_length=200)


class WebhookOut(BaseModel):
    id: str
    url: str
    events: list[str]
    active: bool
    description: str
    created_at: datetime


class WebhookCreated(WebhookOut):
    """Returned exactly once on creation; carries the plaintext signing secret."""

    secret: str


class WebhookDeliveryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    endpoint_id: str
    event: str
    status: str
    attempts: int
    last_response_status: int | None
    last_error: str | None
    next_attempt_at: datetime | None
    created_at: datetime
    delivered_at: datetime | None


# ── admin ────────────────────────────────────────────────────────────


class OrganizationCreate(BaseModel):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_\-]+$")
    name: str = Field(min_length=1, max_length=200)
    contact_email: str = Field(default="", max_length=200)
    rate_limit_per_minute: int = Field(default=0, ge=0, le=1_000_000)


class OrganizationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    contact_email: str
    active: bool
    rate_limit_per_minute: int
    created_at: datetime


class ApiKeyCreate(BaseModel):
    org_id: str = Field(min_length=1, max_length=64)
    label: str = Field(default="", max_length=120)
    scope: Literal["read_only", "read_write", "admin"] = "read_write"


class ApiKeyCreated(BaseModel):
    id: str
    raw: str
    org_id: str
    label: str
    scope: str
    created_at: datetime


class ApiKeyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    org_id: str
    label: str
    scope: str
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None
