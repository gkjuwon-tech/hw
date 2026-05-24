"""Inspection: score a single frame against a calibrated baseline."""

from __future__ import annotations

import time
from datetime import datetime, timezone

import numpy as np
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.events import bus
from app.core.metrics import (
    drift_z_gauge,
    inspection_latency_seconds,
    inspection_score,
    inspections_total,
)
from app.core.security import AuthContext, require_write_scope
from app.core.storage import drift_store, load_baseline
from app.core.webhooks import enqueue as enqueue_webhook
from app.db import Inspection, Line, get_session
from app.schemas import FrameIn, InspectResponse

router = APIRouter(prefix="/v1/lines/{line_id}/inspect", tags=["inspect"])


@router.post("", response_model=InspectResponse)
async def inspect_frame(
    line_id: str,
    payload: FrameIn,
    background: BackgroundTasks,
    include_heatmap: bool = Query(default=False),
    auth: AuthContext = Depends(require_write_scope),
    session: AsyncSession = Depends(get_session),
) -> InspectResponse:
    line = await session.get(Line, line_id)
    if line is None or line.org_id != auth.org_id:
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
    started = time.perf_counter()
    result = baseline.score(arr, sigma_threshold=settings.anomaly_sigma_threshold)
    inspection_latency_seconds.labels(line_id=line_id).observe(time.perf_counter() - started)

    tracker = drift_store.get(auth.org_id, line_id)
    drift_z = tracker.observe(result.score)

    threshold_hits = max(line.threshold_hits, int(0.01 * arr.size))
    verdict = "fail" if result.score > line.threshold_score or result.hits > threshold_hits else "pass"

    inspection = Inspection(
        org_id=auth.org_id,
        line_id=line_id,
        score=result.score,
        hits=result.hits,
        cell_score_max=result.cell_score_max,
        verdict=verdict,
        drift_z=drift_z,
    )
    session.add(inspection)
    line.drift = float(result.score)
    line.drift_z = float(drift_z)
    await session.commit()

    inspections_total.labels(
        org_id=auth.org_id, line_id=line_id, verdict=verdict
    ).inc()
    inspection_score.labels(org_id=auth.org_id, line_id=line_id).observe(result.score)
    drift_z_gauge.labels(org_id=auth.org_id, line_id=line_id).set(drift_z)

    payload_out: dict[str, object] = {
        "line_id": line_id,
        "score": result.score,
        "hits": result.hits,
        "cell_score_max": result.cell_score_max,
        "verdict": verdict,
        "drift_z": drift_z,
        "features": result.frame_features,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    if include_heatmap:
        payload_out["heatmap"] = result.heatmap

    bus.publish(line_id, payload_out)

    if verdict == "fail":
        background.add_task(
            enqueue_webhook,
            auth.org_id,
            "inspection.failed",
            {**payload_out, "org_id": auth.org_id},
        )
    if drift_z >= settings.drift_alert_z:
        background.add_task(
            enqueue_webhook,
            auth.org_id,
            "drift.alert",
            {
                "line_id": line_id,
                "org_id": auth.org_id,
                "drift_z": drift_z,
                "rolling_score": result.score,
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    return InspectResponse(
        line_id=line_id,
        score=result.score,
        hits=result.hits,
        cell_score_max=result.cell_score_max,
        verdict=verdict,
        drift_z=drift_z,
        features=result.frame_features,
        heatmap=result.heatmap if include_heatmap else None,
    )
