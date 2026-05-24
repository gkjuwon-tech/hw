"""Pydantic schemas for the public API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class LineCreate(BaseModel):
    id: str = Field(min_length=1, max_length=64, pattern=r"^[A-Za-z0-9_\-]+$")
    customer_tag: str = Field(default="", max_length=128)
    rows: int = Field(gt=0, le=512)
    cols: int = Field(gt=0, le=512)


class LineOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    customer_tag: str
    rows: int
    cols: int
    status: str
    created_at: datetime
    calibrated_at: datetime | None = None
    n_samples: int
    drift: float


class FrameIn(BaseModel):
    """A single tactile frame.

    ``data`` is a row-major list of length ``rows * cols``. Values are 0..255
    (8-bit) but we accept floats so a host with calibrated raw counts can
    upsample.
    """

    data: list[float]


class CalibrateRequest(BaseModel):
    n_samples: int | None = Field(
        default=None,
        ge=1,
        le=64,
        description="Number of buffered samples to use (most recent). Default: all.",
    )


class CalibrateResponse(BaseModel):
    line_id: str
    n_samples: int
    rows: int
    cols: int
    mean_min: float
    mean_max: float


class InspectResponse(BaseModel):
    line_id: str
    score: float
    hits: int
    cell_score_max: float
    verdict: str
    features: dict[str, float]


class EventOut(BaseModel):
    line_id: str
    score: float
    hits: int
    verdict: str
    created_at: datetime
