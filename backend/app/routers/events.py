"""Server-Sent Events stream for dashboards."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.events import bus
from app.db import Line, get_session

router = APIRouter(prefix="/v1/lines/{line_id}/events", tags=["events"])


@router.get("")
async def stream_events(
    line_id: str, session: AsyncSession = Depends(get_session)
) -> StreamingResponse:
    line = await session.get(Line, line_id)
    if line is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "line not found")

    return StreamingResponse(
        bus.subscribe(line_id),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
