"""Edge appliance enrollment, heartbeat, and live telemetry.

An *Edge* is a Tactile Edge box (Jetson Orin Nano class) physically deployed
in a customer facility. Edges are how we close the loop with real hardware:
the on-device ``edge_agent`` package reads tactile frames from the
USB-CDC-attached scanner MCU, runs local inference, and POSTs both the
inspection events and a periodic heartbeat back to this service.

Endpoints:

  ``POST   /v1/edges``                   — enroll a new Edge (operator action)
  ``GET    /v1/edges``                   — list edges scoped to the auth'd org
  ``GET    /v1/edges/{edge_id}``         — single edge with current metrics
  ``PATCH  /v1/edges/{edge_id}``         — relabel hostname/site
  ``DELETE /v1/edges/{edge_id}``         — decommission
  ``POST   /v1/edges/{edge_id}/heartbeat``
                                         — agent-side telemetry tick
  ``GET    /v1/edges/{edge_id}/telemetry``
                                         — SSE stream of heartbeats (fleet console)
  ``GET    /v1/edges/{edge_id}/telemetry/recent``
                                         — last N heartbeats (replay for late
                                           subscribers)
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.events import bus
from app.core.security import AuthContext, require_org, require_write_scope
from app.db import Edge, get_session
from app.schemas import EdgeCreate, EdgeHeartbeat, EdgeOut, EdgeUpdate

router = APIRouter(prefix="/v1/edges", tags=["edges"])


def _telemetry_topic(edge_id: str) -> str:
    """Per-edge SSE topic key. Distinct from the per-line inspection bus."""
    return f"edge:{edge_id}:telemetry"


@router.post("", response_model=EdgeOut, status_code=status.HTTP_201_CREATED)
async def enroll_edge(
    payload: EdgeCreate,
    auth: AuthContext = Depends(require_write_scope),
    session: AsyncSession = Depends(get_session),
) -> Edge:
    """Legacy edge enrollment path.

    In production this should be disabled (``CONET_LEGACY_EDGE_ENROLL=false``)
    and operators should use the two-step claim-redeem flow
    (``POST /v1/claims`` + ``POST /v1/claims/redeem``) which validates the
    physical device's serial and firmware version.

    Even when enabled, this path now requires a non-empty serial so an
    operator can't enroll a phantom edge by typing a random ID.
    """
    if not settings.legacy_edge_enroll_enabled:
        raise HTTPException(
            status.HTTP_410_GONE,
            "legacy edge enrollment disabled; use POST /v1/claims + /v1/claims/redeem",
        )

    serial = (payload.serial or "").strip()
    if len(serial) < 4:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            "serial is required (min 4 chars). use claim-redeem for full validation.",
        )

    edge = Edge(
        id=payload.id,
        org_id=auth.org_id,
        hostname=payload.hostname,
        serial=serial,
        model=payload.model,
        site=payload.site,
        display_kind=payload.display_kind,
        display_resolution=payload.display_resolution,
    )
    session.add(edge)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "edge already enrolled") from exc
    await session.refresh(edge)
    return edge


@router.get("", response_model=list[EdgeOut])
async def list_edges(
    auth: AuthContext = Depends(require_org),
    session: AsyncSession = Depends(get_session),
) -> list[Edge]:
    result = await session.execute(
        select(Edge).where(Edge.org_id == auth.org_id).order_by(Edge.enrolled_at.desc())
    )
    return list(result.scalars().all())


@router.get("/{edge_id}", response_model=EdgeOut)
async def get_edge(
    edge_id: str,
    auth: AuthContext = Depends(require_org),
    session: AsyncSession = Depends(get_session),
) -> Edge:
    edge = await session.get(Edge, edge_id)
    if edge is None or edge.org_id != auth.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "edge not found")
    return edge


@router.patch("/{edge_id}", response_model=EdgeOut)
async def update_edge(
    edge_id: str,
    payload: EdgeUpdate,
    auth: AuthContext = Depends(require_write_scope),
    session: AsyncSession = Depends(get_session),
) -> Edge:
    edge = await session.get(Edge, edge_id)
    if edge is None or edge.org_id != auth.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "edge not found")
    if payload.hostname is not None:
        edge.hostname = payload.hostname
    if payload.site is not None:
        edge.site = payload.site
    if payload.display_kind is not None:
        edge.display_kind = payload.display_kind
    if payload.display_resolution is not None:
        edge.display_resolution = payload.display_resolution
    await session.commit()
    await session.refresh(edge)
    return edge


@router.delete("/{edge_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_edge(
    edge_id: str,
    auth: AuthContext = Depends(require_write_scope),
    session: AsyncSession = Depends(get_session),
) -> None:
    edge = await session.get(Edge, edge_id)
    if edge is None or edge.org_id != auth.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "edge not found")
    await session.delete(edge)
    await session.commit()


@router.post("/{edge_id}/heartbeat", response_model=EdgeOut)
async def heartbeat(
    edge_id: str,
    payload: EdgeHeartbeat,
    auth: AuthContext = Depends(require_write_scope),
    session: AsyncSession = Depends(get_session),
) -> Edge:
    """Agent-side liveness + metrics tick.

    Updates the persistent ``edges`` row in place AND publishes the same
    payload to the SSE bus so subscribers (fleet console) see it within
    ~1 RTT. A heartbeat with ``frames_per_second == 0`` is treated as
    ``degraded`` rather than ``offline`` — the agent is up but the
    scanner is silent.
    """
    edge = await session.get(Edge, edge_id)
    if edge is None or edge.org_id != auth.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "edge not found")

    edge.firmware_version = payload.firmware_version or edge.firmware_version
    edge.agent_version = payload.agent_version or edge.agent_version
    edge.cpu_pct = payload.cpu_pct
    edge.gpu_pct = payload.gpu_pct
    edge.gpu_temp_c = payload.gpu_temp_c
    edge.cpu_temp_c = payload.cpu_temp_c
    edge.ram_used_mb = payload.ram_used_mb
    edge.ram_total_mb = payload.ram_total_mb
    edge.power_mw = payload.power_mw
    edge.inference_p50_ms = payload.inference_p50_ms
    edge.inference_p99_ms = payload.inference_p99_ms
    edge.frames_per_second = payload.frames_per_second
    edge.display_active = payload.display_active
    edge.display_touch_events_per_min = payload.display_touch_events_per_min
    edge.last_seen_at = datetime.now(timezone.utc)

    if payload.gpu_temp_c >= 90.0 or payload.cpu_temp_c >= 95.0:
        edge.status = "degraded"
    elif payload.frames_per_second <= 0.0 and payload.gpu_pct < 1.0:
        edge.status = "degraded"
    else:
        edge.status = "online"

    await session.commit()
    await session.refresh(edge)

    bus.publish(
        _telemetry_topic(edge_id),
        {
            "edge_id": edge_id,
            "status": edge.status,
            "ts": edge.last_seen_at.isoformat() if edge.last_seen_at else None,
            "cpu_pct": edge.cpu_pct,
            "gpu_pct": edge.gpu_pct,
            "gpu_temp_c": edge.gpu_temp_c,
            "cpu_temp_c": edge.cpu_temp_c,
            "ram_used_mb": edge.ram_used_mb,
            "ram_total_mb": edge.ram_total_mb,
            "power_mw": edge.power_mw,
            "inference_p50_ms": edge.inference_p50_ms,
            "inference_p99_ms": edge.inference_p99_ms,
            "frames_per_second": edge.frames_per_second,
            "firmware_version": edge.firmware_version,
            "agent_version": edge.agent_version,
            "display_active": edge.display_active,
            "display_touch_events_per_min": edge.display_touch_events_per_min,
        },
    )

    return edge


@router.get("/{edge_id}/telemetry")
async def stream_telemetry(
    edge_id: str,
    auth: AuthContext = Depends(require_org),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    edge = await session.get(Edge, edge_id)
    if edge is None or edge.org_id != auth.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "edge not found")

    return StreamingResponse(
        bus.subscribe(_telemetry_topic(edge_id)),
        media_type="text/event-stream",
        headers={
            "cache-control": "no-cache",
            "x-accel-buffering": "no",
        },
    )


@router.get("/{edge_id}/telemetry/recent")
async def recent_telemetry(
    edge_id: str,
    auth: AuthContext = Depends(require_org),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    edge = await session.get(Edge, edge_id)
    if edge is None or edge.org_id != auth.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "edge not found")
    return bus.recent(_telemetry_topic(edge_id))
