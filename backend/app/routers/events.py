"""Server-Sent Events stream for dashboards."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import bus
from app.core.security import AuthContext, require_org
from app.db import Line, get_session

router = APIRouter(prefix="/v1/lines/{line_id}/events", tags=["events"])


@router.get("")
async def stream_events(
    line_id: str,
    auth: AuthContext = Depends(require_org),
    session: AsyncSession = Depends(get_session),
) -> StreamingResponse:
    line = await session.get(Line, line_id)
    if line is None or line.org_id != auth.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "line not found")

    return StreamingResponse(
        bus.subscribe(line_id),
        media_type="text/event-stream",
        headers={
            "cache-control": "no-cache",
            "x-accel-buffering": "no",
        },
    )


@router.get("/recent")
async def recent_events(
    line_id: str,
    auth: AuthContext = Depends(require_org),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    line = await session.get(Line, line_id)
    if line is None or line.org_id != auth.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "line not found")
    return bus.recent(line_id)
