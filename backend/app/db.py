"""Async SQLAlchemy setup and ORM models.

The schema is small but production-shaped:

- ``organizations`` — tenant boundary; every API key and conveyor line is
  scoped to exactly one organization.
- ``api_keys`` — hashed bearer tokens. The plaintext is shown once at
  creation and never persisted.
- ``lines`` — a single registered conveyor / inspection station.
- ``inspections`` — one row per inspected part. Carries the anomaly score
  and the verdict.
- ``webhook_endpoints`` — outbound HTTPS endpoints registered by
  customers to receive signed inspection / drift events.
- ``webhook_deliveries`` — every send attempt, for retry, audit, and
  replay.

The default ``database_url`` is SQLite for local development. Production
uses Postgres; only the DSN has to change.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.core.config import settings

DEFAULT_ORG_ID = "org_default"
DEFAULT_ORG_NAME = "Default workspace"


class Base(DeclarativeBase):
    """SQLAlchemy declarative base."""


class Organization(Base):
    """A customer tenant. Owns lines, API keys, and webhook endpoints."""

    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    contact_email: Mapped[str] = mapped_column(String(200), default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    rate_limit_per_minute: Mapped[int] = mapped_column(Integer, default=0)
    """Per-org override for rate-limiting. ``0`` means use the global default."""

    lines: Mapped[list[Line]] = relationship(back_populates="org", lazy="selectin")


class ApiKey(Base):
    """A hashed bearer token for an organization."""

    __tablename__ = "api_keys"

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    """Public prefix identifier, e.g. ``ctk_live_xxx`` (first 12 chars of the raw key)."""

    org_id: Mapped[str] = mapped_column(String(64), ForeignKey("organizations.id"), index=True)
    label: Mapped[str] = mapped_column(String(120), default="")
    hashed_secret: Mapped[str] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scope: Mapped[str] = mapped_column(String(32), default="read_write")
    """``read_only`` | ``read_write`` | ``admin``."""


class Line(Base):
    """A registered conveyor line."""

    __tablename__ = "lines"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    org_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("organizations.id"), index=True
    )
    customer_tag: Mapped[str] = mapped_column(String(128), default="")
    rows: Mapped[int] = mapped_column(Integer)
    cols: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), default="awaiting_calibration")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    calibrated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    n_samples: Mapped[int] = mapped_column(Integer, default=0)
    drift: Mapped[float] = mapped_column(Float, default=0.0)
    drift_z: Mapped[float] = mapped_column(Float, default=0.0)
    """Z-score of the rolling-mean drift vs. its calibration baseline."""

    threshold_score: Mapped[float] = mapped_column(Float, default=3.0)
    threshold_hits: Mapped[int] = mapped_column(Integer, default=8)

    org: Mapped[Organization] = relationship(back_populates="lines")


class Inspection(Base):
    """A single inspection event."""

    __tablename__ = "inspections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    org_id: Mapped[str] = mapped_column(String(64), index=True)
    line_id: Mapped[str] = mapped_column(String(64), index=True)
    score: Mapped[float] = mapped_column(Float)
    hits: Mapped[int] = mapped_column(Integer)
    cell_score_max: Mapped[float] = mapped_column(Float, default=0.0)
    verdict: Mapped[str] = mapped_column(String(16))  # "pass" | "fail"
    drift_z: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )

    __table_args__ = (
        Index("ix_inspections_line_created", "line_id", "created_at"),
    )


class Edge(Base):
    """A Tactile Edge appliance (Jetson Orin Nano class) deployed in a customer facility.

    One Edge handles one or more Lines. The Edge agent (``edge_agent/``) calls
    ``POST /v1/edges/{edge_id}/heartbeat`` at a regular cadence to report
    liveness and the current hardware metrics (CPU/GPU temp, load, power
    draw). The desktop subscribes to the per-edge SSE stream to render a
    live status panel.
    """

    __tablename__ = "edges"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    org_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("organizations.id"), index=True
    )
    hostname: Mapped[str] = mapped_column(String(120), default="")
    """Operator-visible hostname, e.g. ``edge-floor3-line7``."""
    serial: Mapped[str] = mapped_column(String(64), default="")
    """NVIDIA module serial (from ``/proc/device-tree/serial-number``)."""
    model: Mapped[str] = mapped_column(String(80), default="jetson-orin-nano-8gb")
    site: Mapped[str] = mapped_column(String(120), default="")
    """Free-form facility tag, e.g. ``Plant 2 / Bakery line``."""
    firmware_version: Mapped[str] = mapped_column(String(40), default="")
    """Scanner firmware version reported by the connected MCU, e.g. ``TS-G4 v0.3``."""
    agent_version: Mapped[str] = mapped_column(String(40), default="")
    """``edge_agent`` python package version reported on heartbeat."""
    status: Mapped[str] = mapped_column(String(16), default="offline")
    """``online`` | ``degraded`` | ``offline``."""
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    enrolled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    cpu_pct: Mapped[float] = mapped_column(Float, default=0.0)
    gpu_pct: Mapped[float] = mapped_column(Float, default=0.0)
    gpu_temp_c: Mapped[float] = mapped_column(Float, default=0.0)
    cpu_temp_c: Mapped[float] = mapped_column(Float, default=0.0)
    ram_used_mb: Mapped[int] = mapped_column(Integer, default=0)
    ram_total_mb: Mapped[int] = mapped_column(Integer, default=0)
    power_mw: Mapped[int] = mapped_column(Integer, default=0)
    inference_p50_ms: Mapped[float] = mapped_column(Float, default=0.0)
    inference_p99_ms: Mapped[float] = mapped_column(Float, default=0.0)
    frames_per_second: Mapped[float] = mapped_column(Float, default=0.0)


class MeshSegment(Base):
    """One installed piece of the Tactile Mesh roll, glued to a specific line.

    Customers buy the mesh as a roll (per-meter consumable) and cut segments
    to belt width on site. Each segment has a lot id (for QA traceability),
    an install date (for wear/lifetime accounting), and a row/column count
    (for the per-line geometry).
    """

    __tablename__ = "mesh_segments"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    org_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("organizations.id"), index=True
    )
    line_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("lines.id"), index=True
    )
    edge_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("edges.id"), nullable=True, index=True
    )
    roll_lot: Mapped[str] = mapped_column(String(64), default="")
    """Manufacturer lot for the source roll, e.g. ``TM350-2026W21-A``."""
    belt_width_mm: Mapped[int] = mapped_column(Integer, default=0)
    length_mm: Mapped[int] = mapped_column(Integer, default=0)
    rows: Mapped[int] = mapped_column(Integer)
    cols: Mapped[int] = mapped_column(Integer)
    installed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expected_lifetime_days: Mapped[int] = mapped_column(Integer, default=180)
    health_pct: Mapped[float] = mapped_column(Float, default=100.0)
    """Operator-visible health 0..100. Drops as dead cells accumulate."""
    dead_cells: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str] = mapped_column(Text, default="")


class WebhookEndpoint(Base):
    """An outbound webhook registered by a customer."""

    __tablename__ = "webhook_endpoints"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    org_id: Mapped[str] = mapped_column(String(64), ForeignKey("organizations.id"), index=True)
    url: Mapped[str] = mapped_column(Text)
    secret: Mapped[str] = mapped_column(String(96))
    """HMAC-SHA256 signing secret. Shared with the customer; never re-shown."""

    events: Mapped[str] = mapped_column(
        String(256),
        default="inspection.failed,drift.alert",
        doc="Comma-separated list of event names to receive.",
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    description: Mapped[str] = mapped_column(String(200), default="")

    __table_args__ = (UniqueConstraint("org_id", "url", name="uq_webhook_org_url"),)


class WebhookDelivery(Base):
    """A single delivery attempt against a webhook endpoint."""

    __tablename__ = "webhook_deliveries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    endpoint_id: Mapped[str] = mapped_column(String(36), ForeignKey("webhook_endpoints.id"), index=True)
    org_id: Mapped[str] = mapped_column(String(64), index=True)
    event: Mapped[str] = mapped_column(String(64))
    payload: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(16), default="pending", index=True)
    """``pending`` | ``succeeded`` | ``failed`` | ``dead``."""

    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_response_status: Mapped[int | None] = mapped_column(Integer)
    last_error: Mapped[str | None] = mapped_column(Text)
    next_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


# ── engine / session ─────────────────────────────────────────────────


_engine = create_async_engine(settings.database_url, echo=False, future=True)
_session_factory = async_sessionmaker(_engine, expire_on_commit=False)


async def init_db() -> None:
    """Create tables if they don't exist and seed the default organization."""
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _seed_default_org()


async def _seed_default_org() -> None:
    """Ensure a fallback organization exists for unauthenticated dev use."""
    async with _session_factory() as session:
        existing = await session.get(Organization, DEFAULT_ORG_ID)
        if existing is None:
            session.add(
                Organization(
                    id=DEFAULT_ORG_ID,
                    name=DEFAULT_ORG_NAME,
                    contact_email="dev@conet.local",
                    active=True,
                )
            )
            await session.commit()


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding an async session."""
    async with _session_factory() as session:
        yield session


def session_factory() -> async_sessionmaker[AsyncSession]:
    """Direct access for background workers (not request-scoped)."""
    return _session_factory


async def dispose_engine() -> None:
    await _engine.dispose()
