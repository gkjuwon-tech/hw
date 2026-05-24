"""Inspection: score a single frame against a calibrated baseline."""

from __future__ import annotations

from datetime import datetime, timezone

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.events import bus
from app.core.storage import load_baseline
from app.db import Inspection, Line, get_session
from app.schemas import FrameIn, InspectResponse

router = APIRouter(prefix="/v1/lines/{line_id}/inspect", tags=["inspect"])


@router.post("", response_model=InspectResponse)
async def inspect_frame(
    line_id: str,
    payload: FrameIn,
    session: AsyncSession = Depends(get_session),
) -> InspectResponse:
    line = await session.get(Line, line_id)
    if line is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "line not found")

    baseline = load_baseline(line_id)
    if baseline is None:
        raise HTTPException(
            status.HTTP_409_CONFLICT, "line has no calibration baseline yet"
        )

    expected = line.rows * line.cols
    if len(payload.data) != expected:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"expected {expected} values, got {len(payload.data)}",
        )

    arr = np.asarray(payload.data, dtype=np.float32).reshape(line.rows, line.cols)
    result = baseline.score(arr, sigma_threshold=settings.anomaly_sigma_threshold)

    # Reasonable threshold for the analytical baseline. Real customers will tune
    # this against a small bad-sample set.
    verdict = "fail" if result.score > 3.0 or result.hits > max(8, 0.01 * arr.size) else "pass"

    inspection = Inspection(
        line_id=line_id,
        score=result.score,
        hits=result.hits,
        verdict=verdict,
    )
    session.add(inspection)
    await session.commit()

    payload_out = {
        "line_id": line_id,
        "score": result.score,
        "hits": result.hits,
        "cell_score_max": result.cell_score_max,
        "verdict": verdict,
        "features": result.frame_features,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    bus.publish(line_id, payload_out)

    return InspectResponse(
        line_id=line_id,
        score=result.score,
        hits=result.hits,
        cell_score_max=result.cell_score_max,
        verdict=verdict,
        features=result.frame_features,
    )
