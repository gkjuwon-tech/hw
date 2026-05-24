"""Calibration: build a one-class baseline from buffered samples."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.anomaly import Baseline
from app.core.config import settings
from app.core.security import AuthContext, require_write_scope
from app.core.storage import calibration_buffer, drift_store, save_baseline
from app.db import Line, get_session
from app.schemas import CalibrateRequest, CalibrateResponse

router = APIRouter(prefix="/v1/lines/{line_id}/calibrate", tags=["calibrate"])


@router.post("", response_model=CalibrateResponse)
async def calibrate_line(
    line_id: str,
    payload: CalibrateRequest,
    auth: AuthContext = Depends(require_write_scope),
    session: AsyncSession = Depends(get_session),
) -> CalibrateResponse:
    line = await session.get(Line, line_id)
    if line is None or line.org_id != auth.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "line not found")

    have = calibration_buffer.size(line_id)
    if have < settings.min_calibration_samples:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"need at least {settings.min_calibration_samples} buffered samples; have {have}",
        )

    n = payload.n_samples or have
    samples = calibration_buffer.take(line_id, n)
    if not samples:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no samples buffered")

    baseline = Baseline.fit(samples)
    save_baseline(line_id, baseline)

    # Seed the drift tracker with the calibration distribution's self-score, so
    # the first few inspections of a real run aren't reported as drifting.
    cohort_scores = [
        baseline.score(s, sigma_threshold=settings.anomaly_sigma_threshold).score
        for s in samples
    ]
    tracker = drift_store.get(auth.org_id, line_id)
    tracker.calibrate(cohort_scores)
    tracker.reset()

    line.status = "live"
    line.calibrated_at = datetime.now(timezone.utc)
    line.n_samples = baseline.n_samples
    line.drift = 0.0
    line.drift_z = 0.0
    await session.commit()

    return CalibrateResponse(
        line_id=line_id,
        n_samples=baseline.n_samples,
        rows=baseline.rows,
        cols=baseline.cols,
        mean_min=float(baseline.mean.min()),
        mean_max=float(baseline.mean.max()),
    )
