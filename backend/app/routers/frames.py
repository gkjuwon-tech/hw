"""Frame ingestion (calibration buffer)."""

from __future__ import annotations

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import AuthContext, require_write_scope
from app.core.storage import calibration_buffer
from app.db import Line, get_session
from app.schemas import FrameIn

router = APIRouter(prefix="/v1/lines/{line_id}/frames", tags=["frames"])


async def _frame_to_array(line: Line, payload: FrameIn) -> np.ndarray:
    expected = line.rows * line.cols
    if len(payload.data) != expected:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"expected {expected} values ({line.rows}x{line.cols}), got {len(payload.data)}",
        )
    return np.asarray(payload.data, dtype=np.float32).reshape(line.rows, line.cols)


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def ingest_frame(
    line_id: str,
    payload: FrameIn,
    auth: AuthContext = Depends(require_write_scope),
    session: AsyncSession = Depends(get_session),
) -> dict[str, int | str]:
    """Append a frame to the in-memory calibration buffer."""
    line = await session.get(Line, line_id)
    if line is None or line.org_id != auth.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "line not found")

    arr = await _frame_to_array(line, payload)
    size = calibration_buffer.append(line_id, arr)
    return {"line_id": line_id, "buffered": size}
