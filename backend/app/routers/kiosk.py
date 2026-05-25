"""On-device touch-display kiosk endpoints.

The Tactile Edge box ships with an integrated touch display. The on-device
``edge_agent`` serves the actual kiosk HTML/JS over loopback (so the kiosk
works even when the factory network is down), but the **configuration**
the kiosk renders against \u2014 line label, brand color, locale, which
features to show \u2014 is owned by the cloud so the operator's IT can roll
out fleet-wide UI changes without SSH-ing into every box.

Two endpoints live here:

*   ``GET /v1/kiosk/{edge_id}/config`` \u2014 fetch the kiosk config the
    on-device Chromium should render against. The edge_agent polls this
    every ``poll_interval_s`` seconds and writes the response to
    ``/etc/conet/kiosk.json`` so the kiosk has a sane default at boot
    even when the cloud is unreachable.
*   ``POST /v1/kiosk/{edge_id}/touch-event`` \u2014 the kiosk reports each
    coarse-grained interaction (calibrate button, recipe switch, etc.)
    for fleet analytics. Touch coordinates are deliberately *not*
    collected \u2014 only the action name.

This router is **read-mostly** and is the primary candidate for the
Cloudflare Workers ``edge_api/`` cache layer. The worker can hold the
config for ``poll_interval_s`` seconds and absorb the polling load.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import AuthContext, require_org
from app.db import Edge, get_session
from app.schemas import KioskConfig

router = APIRouter(prefix="/v1/kiosk", tags=["kiosk"])


class TouchEvent(BaseModel):
    """A single coarse-grained kiosk interaction."""

    action: str = Field(min_length=1, max_length=64)
    """Action identifier, e.g. ``calibrate.start``, ``recipe.switch``,
    ``inspection.acknowledge``."""

    detail: str = Field(default="", max_length=256)
    line_id: str | None = Field(default=None, max_length=64)


class TouchEventAck(BaseModel):
    received: bool = True


@router.get("/{edge_id}/config", response_model=KioskConfig)
async def get_kiosk_config(
    edge_id: str,
    auth: AuthContext = Depends(require_org),
    session: AsyncSession = Depends(get_session),
) -> KioskConfig:
    """Return the kiosk render config for the given edge.

    Cacheable for ``poll_interval_s`` seconds. The current implementation
    returns the default config keyed off the edge's enrolled ``site``
    field; a follow-up will let operators override brand color, locale,
    and feature flags per-site from the admin console.
    """
    edge = await session.get(Edge, edge_id)
    if edge is None or edge.org_id != auth.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "edge not found")

    return KioskConfig(
        edge_id=edge.id,
        line_id=None,
        line_label=edge.hostname or edge.id,
        site=edge.site,
    )


@router.post(
    "/{edge_id}/touch-event",
    response_model=TouchEventAck,
    status_code=status.HTTP_202_ACCEPTED,
)
async def record_touch_event(
    edge_id: str,
    payload: TouchEvent,
    auth: AuthContext = Depends(require_org),
    session: AsyncSession = Depends(get_session),
) -> TouchEventAck:
    """Acknowledge an on-device kiosk interaction.

    Touch coordinates are intentionally NOT captured \u2014 only the action
    name, an optional detail string, and the line context. This is for
    fleet analytics ("which screens get touched most often?") rather
    than user tracking.
    """
    edge = await session.get(Edge, edge_id)
    if edge is None or edge.org_id != auth.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "edge not found")
    # The detail and line_id are accepted but not yet persisted; a
    # follow-up will route them through the existing webhook bus so
    # customers can react to kiosk interactions.
    _ = (payload.detail, payload.line_id)
    return TouchEventAck(received=True)


@router.get("/{edge_id}/index.html", response_class=None)
async def get_kiosk_landing(
    edge_id: str,
    auth: AuthContext = Depends(require_org),
    session: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """Diagnostic helper \u2014 returns a JSON summary of what the kiosk would
    render. The actual HTML is served by the on-device ``edge_agent`` over
    loopback (``http://127.0.0.1:8088/kiosk/index.html``); this endpoint
    exists so support can sanity-check the cloud-side config from
    anywhere on the fleet network.
    """
    edge = await session.get(Edge, edge_id)
    if edge is None or edge.org_id != auth.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "edge not found")
    return {
        "edge_id": edge.id,
        "display_kind": edge.display_kind,
        "display_resolution": edge.display_resolution,
        "display_active": edge.display_active,
        "kiosk_url": "http://127.0.0.1:8088/kiosk/index.html",
        "fleet_console_url": f"/admin/edges/{edge.id}",
    }
