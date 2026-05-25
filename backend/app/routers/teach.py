"""Teach endpoint — first-run 5-sample AI learning + line activation.

This is the production version of the calibration flow. Instead of
manually buffering frames and then calling /calibrate, the operator
uses the Teach Wizard: capture 5 known-good samples one at a time,
the backend tracks progress, runs the fit, and arms the line in one go.

Endpoints:

  ``POST   /v1/edges/{edge_id}/teach/start``   — begin a teach session
  ``POST   /v1/edges/{edge_id}/teach/capture``  — capture one sample frame
  ``POST   /v1/edges/{edge_id}/teach/finish``   — finalize training & arm the line
  ``GET    /v1/edges/{edge_id}/teach/status``   — current teach session progress
  ``DELETE /v1/edges/{edge_id}/teach``           — abort teach session
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.anomaly import Baseline
from app.core.config import settings
from app.core.security import AuthContext, require_write_scope
from app.core.storage import calibration_buffer, drift_store, save_baseline
from app.db import Edge, Line, get_session

router = APIRouter(prefix="/v1/edges/{edge_id}/teach", tags=["teach"])

# In-memory teach sessions (keyed by edge_id)
_sessions: dict[str, TeachSession] = {}

REQUIRED_SAMPLES = 5


class TeachSession:
    """State for an in-progress teach/training session."""

    def __init__(self, edge_id: str, line_id: str, rows: int, cols: int) -> None:
        self.edge_id = edge_id
        self.line_id = line_id
        self.rows = rows
        self.cols = cols
        self.samples: list[np.ndarray] = []
        self.started_at = time.time()
        self.status = "in_progress"  # in_progress | completed | failed

    @property
    def captured(self) -> int:
        return len(self.samples)

    @property
    def remaining(self) -> int:
        return max(0, REQUIRED_SAMPLES - self.captured)

    def is_complete(self) -> bool:
        return self.captured >= REQUIRED_SAMPLES


# ── schemas ──────────────────────────────────────────────────────────


class TeachStartRequest(BaseModel):
    line_id: str = Field(min_length=1, max_length=64)


class TeachStartResponse(BaseModel):
    edge_id: str
    line_id: str
    required_samples: int
    status: str
    message: str


class TeachCaptureRequest(BaseModel):
    data: list[float] = Field(min_length=1, max_length=262144)


class TeachCaptureResponse(BaseModel):
    edge_id: str
    line_id: str
    captured: int
    remaining: int
    status: str
    message: str


class TeachFinishResponse(BaseModel):
    edge_id: str
    line_id: str
    n_samples: int
    rows: int
    cols: int
    mean_min: float
    mean_max: float
    line_status: str
    message: str


class TeachStatusResponse(BaseModel):
    edge_id: str
    line_id: str | None
    captured: int
    required: int
    remaining: int
    status: str
    elapsed_s: float


# ── routes ───────────────────────────────────────────────────────────


@router.post("/start", response_model=TeachStartResponse, status_code=status.HTTP_201_CREATED)
async def teach_start(
    edge_id: str,
    payload: TeachStartRequest,
    auth: AuthContext = Depends(require_write_scope),
    session: AsyncSession = Depends(get_session),
) -> TeachStartResponse:
    """Begin a teach session on an edge for a specific line.

    Validates that the edge exists, the line exists and belongs to the same
    org, and that no teach session is already running on this edge.
    """
    edge = await session.get(Edge, edge_id)
    if edge is None or edge.org_id != auth.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "edge not found")

    line = await session.get(Line, payload.line_id)
    if line is None or line.org_id != auth.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "line not found")

    if edge_id in _sessions and _sessions[edge_id].status == "in_progress":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"teach session already active on edge {edge_id} for line {_sessions[edge_id].line_id}",
        )

    _sessions[edge_id] = TeachSession(
        edge_id=edge_id,
        line_id=payload.line_id,
        rows=line.rows,
        cols=line.cols,
    )

    return TeachStartResponse(
        edge_id=edge_id,
        line_id=payload.line_id,
        required_samples=REQUIRED_SAMPLES,
        status="in_progress",
        message=f"Teach session started. Capture {REQUIRED_SAMPLES} known-good samples.",
    )


@router.post("/capture", response_model=TeachCaptureResponse)
async def teach_capture(
    edge_id: str,
    payload: TeachCaptureRequest,
    auth: AuthContext = Depends(require_write_scope),
    session: AsyncSession = Depends(get_session),
) -> TeachCaptureResponse:
    """Capture one sample frame during the teach session.

    Validates frame dimensions match the line geometry. Each captured
    frame is stored in memory until finalization.
    """
    edge = await session.get(Edge, edge_id)
    if edge is None or edge.org_id != auth.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "edge not found")

    ts = _sessions.get(edge_id)
    if ts is None or ts.status != "in_progress":
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no active teach session on this edge")

    expected = ts.rows * ts.cols
    if len(payload.data) != expected:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"frame size mismatch: expected {expected} ({ts.rows}x{ts.cols}), got {len(payload.data)}",
        )

    if ts.is_complete():
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"already captured {REQUIRED_SAMPLES} samples; call /teach/finish to finalize",
        )

    arr = np.asarray(payload.data, dtype=np.float32).reshape(ts.rows, ts.cols)
    ts.samples.append(arr)

    # Also buffer into the calibration store for compatibility
    calibration_buffer.append(ts.line_id, arr)

    msg = (
        f"Sample {ts.captured}/{REQUIRED_SAMPLES} captured."
        if ts.remaining > 0
        else f"All {REQUIRED_SAMPLES} samples captured. Ready to finalize."
    )

    return TeachCaptureResponse(
        edge_id=edge_id,
        line_id=ts.line_id,
        captured=ts.captured,
        remaining=ts.remaining,
        status="in_progress" if ts.remaining > 0 else "ready",
        message=msg,
    )


@router.post("/finish", response_model=TeachFinishResponse)
async def teach_finish(
    edge_id: str,
    auth: AuthContext = Depends(require_write_scope),
    session: AsyncSession = Depends(get_session),
) -> TeachFinishResponse:
    """Finalize the teach session: fit baseline, arm the line.

    Requires all 5 samples to have been captured. Computes the one-class
    baseline, saves it, seeds the drift tracker, and sets line status to 'live'.
    """
    edge = await session.get(Edge, edge_id)
    if edge is None or edge.org_id != auth.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "edge not found")

    ts = _sessions.get(edge_id)
    if ts is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "no teach session on this edge")

    if not ts.is_complete():
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"need {REQUIRED_SAMPLES} samples, only have {ts.captured}",
        )

    line = await session.get(Line, ts.line_id)
    if line is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "line no longer exists")

    # Fit the baseline
    baseline = Baseline.fit(ts.samples)
    save_baseline(ts.line_id, baseline)

    # Seed drift tracker
    cohort_scores = [
        baseline.score(s, sigma_threshold=settings.anomaly_sigma_threshold).score
        for s in ts.samples
    ]
    tracker = drift_store.get(auth.org_id, ts.line_id)
    tracker.calibrate(cohort_scores)
    tracker.reset()

    # Arm the line
    line.status = "live"
    line.calibrated_at = datetime.now(timezone.utc)
    line.n_samples = baseline.n_samples
    line.drift = 0.0
    line.drift_z = 0.0
    await session.commit()

    # Mark session as complete
    ts.status = "completed"

    return TeachFinishResponse(
        edge_id=edge_id,
        line_id=ts.line_id,
        n_samples=baseline.n_samples,
        rows=baseline.rows,
        cols=baseline.cols,
        mean_min=float(baseline.mean.min()),
        mean_max=float(baseline.mean.max()),
        line_status="live",
        message="Training complete. Line is now live and inspecting.",
    )


@router.get("/status", response_model=TeachStatusResponse)
async def teach_status(
    edge_id: str,
    auth: AuthContext = Depends(require_write_scope),
    session: AsyncSession = Depends(get_session),
) -> TeachStatusResponse:
    """Get the current state of the teach session on this edge."""
    edge = await session.get(Edge, edge_id)
    if edge is None or edge.org_id != auth.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "edge not found")

    ts = _sessions.get(edge_id)
    if ts is None:
        return TeachStatusResponse(
            edge_id=edge_id,
            line_id=None,
            captured=0,
            required=REQUIRED_SAMPLES,
            remaining=REQUIRED_SAMPLES,
            status="idle",
            elapsed_s=0.0,
        )

    return TeachStatusResponse(
        edge_id=edge_id,
        line_id=ts.line_id,
        captured=ts.captured,
        required=REQUIRED_SAMPLES,
        remaining=ts.remaining,
        status=ts.status,
        elapsed_s=round(time.time() - ts.started_at, 1),
    )


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def teach_abort(
    edge_id: str,
    auth: AuthContext = Depends(require_write_scope),
    session: AsyncSession = Depends(get_session),
) -> None:
    """Abort an in-progress teach session."""
    edge = await session.get(Edge, edge_id)
    if edge is None or edge.org_id != auth.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "edge not found")

    if edge_id in _sessions:
        del _sessions[edge_id]
