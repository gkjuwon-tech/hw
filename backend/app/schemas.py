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
    # ``pilot`` is kept for back-compat with v0 clients — it is normalized
    # to ``basic`` server-side. ``basic | production | fleet`` is the
    # current public set of Edge Care tiers.
    care_tier: Literal["basic", "production", "fleet", "pilot"] = "production"
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


class PricingCareBreakdown(BaseModel):
    tier_id: str
    tier_label: str
    base: PricingMoney
    extra_lines: int
    extra_lines_total: PricingMoney
    overage_inspections: int
    overage_total: PricingMoney
    total_monthly: PricingMoney


# Back-compat alias — v0 clients deserialize against ``PricingCloudBreakdown``.
PricingCloudBreakdown = PricingCareBreakdown


class PricingQuoteResponse(BaseModel):
    lines: list[PricingLineBreakdown]
    care: PricingCareBreakdown
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


# ── edges (Tactile Edge appliances) ──────────────────────────────────


class EdgeCreate(BaseModel):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_\-]+$")
    hostname: str = Field(default="", max_length=120)
    serial: str = Field(default="", max_length=64)
    model: str = Field(default="jetson-orin-nano-8gb", max_length=80)
    site: str = Field(default="", max_length=120)
    display_kind: str = Field(default="hdmi-touch-7in", max_length=40)
    display_resolution: str = Field(default="1024x600", max_length=20)


class EdgeUpdate(BaseModel):
    hostname: str | None = Field(default=None, max_length=120)
    site: str | None = Field(default=None, max_length=120)
    display_kind: str | None = Field(default=None, max_length=40)
    display_resolution: str | None = Field(default=None, max_length=20)


class EdgeHeartbeat(BaseModel):
    """Posted by the on-device ``edge_agent`` every ``heartbeat_period_s`` seconds."""

    firmware_version: str = Field(default="", max_length=40)
    agent_version: str = Field(default="", max_length=40)
    cpu_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    gpu_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    gpu_temp_c: float = Field(default=0.0, ge=-40.0, le=200.0)
    cpu_temp_c: float = Field(default=0.0, ge=-40.0, le=200.0)
    ram_used_mb: int = Field(default=0, ge=0, le=1_048_576)
    ram_total_mb: int = Field(default=0, ge=0, le=1_048_576)
    power_mw: int = Field(default=0, ge=0, le=1_000_000)
    inference_p50_ms: float = Field(default=0.0, ge=0.0, le=60_000.0)
    inference_p99_ms: float = Field(default=0.0, ge=0.0, le=60_000.0)
    frames_per_second: float = Field(default=0.0, ge=0.0, le=10_000.0)
    display_active: bool = Field(
        default=False,
        description=(
            "True when the on-device Chromium kiosk is rendering the operator UI "
            "on the integrated touch display. False when the display is asleep, "
            "disconnected, or the kiosk service is stopped."
        ),
    )
    display_touch_events_per_min: float = Field(
        default=0.0, ge=0.0, le=10_000.0,
        description="Touch events / minute on the integrated display. 0 = idle.",
    )


class EdgeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    org_id: str
    hostname: str
    serial: str
    model: str
    site: str
    firmware_version: str
    agent_version: str
    status: str
    last_seen_at: datetime | None
    enrolled_at: datetime
    cpu_pct: float
    gpu_pct: float
    gpu_temp_c: float
    cpu_temp_c: float
    ram_used_mb: int
    ram_total_mb: int
    power_mw: int
    inference_p50_ms: float
    inference_p99_ms: float
    frames_per_second: float
    display_kind: str
    display_resolution: str
    display_active: bool
    display_touch_events_per_min: float


# ── kiosk (on-device touch display) ──────────────────────────────────


class KioskConfig(BaseModel):
    """Configuration handed to the on-device Chromium kiosk on startup.

    The kiosk fetches this once at boot and re-polls every
    ``poll_interval_s`` seconds. The values below are the only things the
    kiosk needs to render a useful operator UI — the actual live data is
    streamed from the local ``edge_agent`` over loopback.
    """

    edge_id: str
    line_id: str | None = None
    line_label: str = ""
    site: str = ""
    brand_color: str = Field(default="#0b0c0a", pattern=r"^#[0-9A-Fa-f]{6}$")
    locale: Literal["ko-KR", "en-US", "ja-JP", "de-DE"] = "ko-KR"
    poll_interval_s: int = Field(default=15, ge=1, le=3600)
    show_drift: bool = True
    show_calibration_button: bool = True
    show_recipe_picker: bool = True
    kiosk_index_url: str = Field(
        default="http://127.0.0.1:8088/kiosk/index.html",
        description=(
            "URL the on-device Chromium loads at boot. Defaults to the "
            "edge_agent's loopback HTTP server so the kiosk works without "
            "any cloud connectivity."
        ),
    )


# ── mesh segments (installed roll-mesh pieces) ───────────────────────


class MeshSegmentCreate(BaseModel):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_\-]+$")
    line_id: str = Field(min_length=1, max_length=64)
    edge_id: str | None = Field(default=None, max_length=64)
    roll_lot: str = Field(default="", max_length=64)
    belt_width_mm: int = Field(default=0, ge=0, le=2_000)
    length_mm: int = Field(default=0, ge=0, le=10_000)
    rows: int = Field(gt=0, le=512)
    cols: int = Field(gt=0, le=512)
    expected_lifetime_days: int = Field(default=180, ge=1, le=3650)
    notes: str = Field(default="", max_length=4000)


class MeshSegmentUpdate(BaseModel):
    edge_id: str | None = Field(default=None, max_length=64)
    health_pct: float | None = Field(default=None, ge=0.0, le=100.0)
    dead_cells: int | None = Field(default=None, ge=0, le=1_000_000)
    notes: str | None = Field(default=None, max_length=4000)


class MeshSegmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    org_id: str
    line_id: str
    edge_id: str | None
    roll_lot: str
    belt_width_mm: int
    length_mm: int
    rows: int
    cols: int
    installed_at: datetime
    expected_lifetime_days: int
    health_pct: float
    dead_cells: int
    notes: str
