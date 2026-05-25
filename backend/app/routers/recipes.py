"""Recipe system — per-product inspection configs (Cognex Job equivalent).

A *Recipe* is a saved, named bundle of inspection parameters for a specific
product. Operators switch lines between recipes when changing products
without re-teaching — same line, different recipe, different thresholds
and ROIs.

Endpoints:

  ``POST   /v1/recipes``                     — create a recipe
  ``GET    /v1/recipes``                     — list recipes (filterable by line)
  ``GET    /v1/recipes/{recipe_id}``         — single recipe
  ``PATCH  /v1/recipes/{recipe_id}``         — edit recipe
  ``DELETE /v1/recipes/{recipe_id}``         — remove recipe
  ``POST   /v1/lines/{line_id}/load_recipe`` — load recipe into a line
"""

from __future__ import annotations

import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import (
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.security import AuthContext, require_org, require_write_scope
from app.db import Base, Line, get_session

router = APIRouter(prefix="/v1/recipes", tags=["recipes"])
line_router = APIRouter(prefix="/v1/lines", tags=["recipes"])


# ── ORM ──────────────────────────────────────────────────────────────


class Recipe(Base):
    """A saved inspection configuration for a specific product."""

    __tablename__ = "recipes"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    org_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("organizations.id"), index=True
    )
    line_id: Mapped[str | None] = mapped_column(
        String(64), ForeignKey("lines.id"), nullable=True, index=True
    )
    """Optional: pin recipe to a specific line. If null, recipe is portable."""

    name: Mapped[str] = mapped_column(String(120))
    product_sku: Mapped[str] = mapped_column(String(64), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    threshold_score: Mapped[float] = mapped_column(Float, default=3.0)
    threshold_hits: Mapped[int] = mapped_column(Integer, default=8)
    sigma_threshold: Mapped[float] = mapped_column(Float, default=3.0)
    drift_alert_z: Mapped[float] = mapped_column(Float, default=2.5)
    # ROI rectangle (normalized 0..1 coords)
    roi_x0: Mapped[float] = mapped_column(Float, default=0.0)
    roi_y0: Mapped[float] = mapped_column(Float, default=0.0)
    roi_x1: Mapped[float] = mapped_column(Float, default=1.0)
    roi_y1: Mapped[float] = mapped_column(Float, default=1.0)
    # Preprocessing chain
    gain: Mapped[float] = mapped_column(Float, default=1.0)
    gamma: Mapped[float] = mapped_column(Float, default=1.0)
    sharpen: Mapped[float] = mapped_column(Float, default=0.0)
    denoise: Mapped[float] = mapped_column(Float, default=0.0)
    # Blob analysis
    blob_min_area: Mapped[int] = mapped_column(Integer, default=4)
    blob_max_area: Mapped[int] = mapped_column(Integer, default=65535)
    rotation_tolerance_deg: Mapped[float] = mapped_column(Float, default=180.0)
    scale_tolerance_pct: Mapped[float] = mapped_column(Float, default=50.0)
    # Trigger / pacing
    trigger_mode: Mapped[str] = mapped_column(String(24), default="continuous")
    """``continuous`` | ``external`` | ``software`` | ``encoder``."""
    debounce_ms: Mapped[int] = mapped_column(Integer, default=50)
    reject_queue_depth: Mapped[int] = mapped_column(Integer, default=8)
    # Lighting (for systems with a strobe output)
    strobe_duty_pct: Mapped[float] = mapped_column(Float, default=50.0)
    strobe_delay_us: Mapped[int] = mapped_column(Integer, default=0)
    # Pass/fail logic builder (simple DSL stored as text)
    logic_dsl: Mapped[str] = mapped_column(
        Text,
        default="score > threshold_score AND hits >= threshold_hits => FAIL",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


# Default recipe field set used both as Pydantic out-shape and for line-load.
class RecipeFields(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    product_sku: str = Field(default="", max_length=64)
    description: str = Field(default="", max_length=4000)
    threshold_score: float = Field(default=3.0, ge=0.0, le=20.0)
    threshold_hits: int = Field(default=8, ge=0, le=10_000)
    sigma_threshold: float = Field(default=3.0, ge=0.5, le=10.0)
    drift_alert_z: float = Field(default=2.5, ge=0.5, le=10.0)
    roi_x0: float = Field(default=0.0, ge=0.0, le=1.0)
    roi_y0: float = Field(default=0.0, ge=0.0, le=1.0)
    roi_x1: float = Field(default=1.0, ge=0.0, le=1.0)
    roi_y1: float = Field(default=1.0, ge=0.0, le=1.0)
    gain: float = Field(default=1.0, ge=0.01, le=10.0)
    gamma: float = Field(default=1.0, ge=0.1, le=5.0)
    sharpen: float = Field(default=0.0, ge=0.0, le=5.0)
    denoise: float = Field(default=0.0, ge=0.0, le=5.0)
    blob_min_area: int = Field(default=4, ge=1, le=1_000_000)
    blob_max_area: int = Field(default=65535, ge=1, le=10_000_000)
    rotation_tolerance_deg: float = Field(default=180.0, ge=0.0, le=180.0)
    scale_tolerance_pct: float = Field(default=50.0, ge=0.0, le=100.0)
    trigger_mode: str = Field(default="continuous", pattern=r"^(continuous|external|software|encoder)$")
    debounce_ms: int = Field(default=50, ge=0, le=10_000)
    reject_queue_depth: int = Field(default=8, ge=1, le=1000)
    strobe_duty_pct: float = Field(default=50.0, ge=0.0, le=100.0)
    strobe_delay_us: int = Field(default=0, ge=0, le=1_000_000)
    logic_dsl: str = Field(
        default="score > threshold_score AND hits >= threshold_hits => FAIL",
        max_length=4000,
    )


class RecipeCreate(RecipeFields):
    line_id: str | None = Field(default=None, max_length=64)


class RecipeUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    product_sku: str | None = Field(default=None, max_length=64)
    description: str | None = Field(default=None, max_length=4000)
    threshold_score: float | None = Field(default=None, ge=0.0, le=20.0)
    threshold_hits: int | None = Field(default=None, ge=0, le=10_000)
    sigma_threshold: float | None = Field(default=None, ge=0.5, le=10.0)
    drift_alert_z: float | None = Field(default=None, ge=0.5, le=10.0)
    roi_x0: float | None = Field(default=None, ge=0.0, le=1.0)
    roi_y0: float | None = Field(default=None, ge=0.0, le=1.0)
    roi_x1: float | None = Field(default=None, ge=0.0, le=1.0)
    roi_y1: float | None = Field(default=None, ge=0.0, le=1.0)
    gain: float | None = Field(default=None, ge=0.01, le=10.0)
    gamma: float | None = Field(default=None, ge=0.1, le=5.0)
    sharpen: float | None = Field(default=None, ge=0.0, le=5.0)
    denoise: float | None = Field(default=None, ge=0.0, le=5.0)
    blob_min_area: int | None = Field(default=None, ge=1, le=1_000_000)
    blob_max_area: int | None = Field(default=None, ge=1, le=10_000_000)
    rotation_tolerance_deg: float | None = Field(default=None, ge=0.0, le=180.0)
    scale_tolerance_pct: float | None = Field(default=None, ge=0.0, le=100.0)
    trigger_mode: str | None = Field(default=None, pattern=r"^(continuous|external|software|encoder)$")
    debounce_ms: int | None = Field(default=None, ge=0, le=10_000)
    reject_queue_depth: int | None = Field(default=None, ge=1, le=1000)
    strobe_duty_pct: float | None = Field(default=None, ge=0.0, le=100.0)
    strobe_delay_us: int | None = Field(default=None, ge=0, le=1_000_000)
    logic_dsl: str | None = Field(default=None, max_length=4000)


class RecipeOut(RecipeFields):
    model_config = ConfigDict(from_attributes=True)

    id: str
    org_id: str
    line_id: str | None
    created_at: datetime
    updated_at: datetime


# ── routes ───────────────────────────────────────────────────────────


def _gen_recipe_id() -> str:
    return "rcp_" + secrets.token_urlsafe(8).replace("_", "").replace("-", "")[:16]


@router.post("", response_model=RecipeOut, status_code=status.HTTP_201_CREATED)
async def create_recipe(
    payload: RecipeCreate,
    auth: AuthContext = Depends(require_write_scope),
    session: AsyncSession = Depends(get_session),
) -> Recipe:
    if payload.line_id is not None:
        line = await session.get(Line, payload.line_id)
        if line is None or line.org_id != auth.org_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "line not found")

    recipe = Recipe(
        id=_gen_recipe_id(),
        org_id=auth.org_id,
        line_id=payload.line_id,
        name=payload.name,
        product_sku=payload.product_sku,
        description=payload.description,
        threshold_score=payload.threshold_score,
        threshold_hits=payload.threshold_hits,
        sigma_threshold=payload.sigma_threshold,
        drift_alert_z=payload.drift_alert_z,
        roi_x0=payload.roi_x0,
        roi_y0=payload.roi_y0,
        roi_x1=payload.roi_x1,
        roi_y1=payload.roi_y1,
        gain=payload.gain,
        gamma=payload.gamma,
        sharpen=payload.sharpen,
        denoise=payload.denoise,
        blob_min_area=payload.blob_min_area,
        blob_max_area=payload.blob_max_area,
        rotation_tolerance_deg=payload.rotation_tolerance_deg,
        scale_tolerance_pct=payload.scale_tolerance_pct,
        trigger_mode=payload.trigger_mode,
        debounce_ms=payload.debounce_ms,
        reject_queue_depth=payload.reject_queue_depth,
        strobe_duty_pct=payload.strobe_duty_pct,
        strobe_delay_us=payload.strobe_delay_us,
        logic_dsl=payload.logic_dsl,
    )
    session.add(recipe)
    await session.commit()
    await session.refresh(recipe)
    return recipe


@router.get("", response_model=list[RecipeOut])
async def list_recipes(
    line_id: str | None = None,
    auth: AuthContext = Depends(require_org),
    session: AsyncSession = Depends(get_session),
) -> list[Recipe]:
    stmt = select(Recipe).where(Recipe.org_id == auth.org_id)
    if line_id is not None:
        stmt = stmt.where((Recipe.line_id == line_id) | (Recipe.line_id.is_(None)))
    stmt = stmt.order_by(Recipe.updated_at.desc())
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.get("/{recipe_id}", response_model=RecipeOut)
async def get_recipe(
    recipe_id: str,
    auth: AuthContext = Depends(require_org),
    session: AsyncSession = Depends(get_session),
) -> Recipe:
    recipe = await session.get(Recipe, recipe_id)
    if recipe is None or recipe.org_id != auth.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "recipe not found")
    return recipe


@router.patch("/{recipe_id}", response_model=RecipeOut)
async def update_recipe(
    recipe_id: str,
    payload: RecipeUpdate,
    auth: AuthContext = Depends(require_write_scope),
    session: AsyncSession = Depends(get_session),
) -> Recipe:
    recipe = await session.get(Recipe, recipe_id)
    if recipe is None or recipe.org_id != auth.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "recipe not found")

    data = payload.model_dump(exclude_unset=True)
    for key, value in data.items():
        setattr(recipe, key, value)
    recipe.updated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(recipe)
    return recipe


@router.delete("/{recipe_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_recipe(
    recipe_id: str,
    auth: AuthContext = Depends(require_write_scope),
    session: AsyncSession = Depends(get_session),
) -> None:
    recipe = await session.get(Recipe, recipe_id)
    if recipe is None or recipe.org_id != auth.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "recipe not found")
    await session.delete(recipe)
    await session.commit()


class LoadRecipeRequest(BaseModel):
    recipe_id: str = Field(min_length=1, max_length=64)


class LoadRecipeResponse(BaseModel):
    line_id: str
    recipe_id: str
    recipe_name: str
    threshold_score: float
    threshold_hits: int


@line_router.post("/{line_id}/load_recipe", response_model=LoadRecipeResponse)
async def load_recipe_into_line(
    line_id: str,
    payload: LoadRecipeRequest,
    auth: AuthContext = Depends(require_write_scope),
    session: AsyncSession = Depends(get_session),
) -> LoadRecipeResponse:
    """Apply the recipe's pass/fail thresholds to the line in one call."""
    line = await session.get(Line, line_id)
    if line is None or line.org_id != auth.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "line not found")

    recipe = await session.get(Recipe, payload.recipe_id)
    if recipe is None or recipe.org_id != auth.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "recipe not found")

    line.threshold_score = recipe.threshold_score
    line.threshold_hits = recipe.threshold_hits
    await session.commit()
    return LoadRecipeResponse(
        line_id=line_id,
        recipe_id=recipe.id,
        recipe_name=recipe.name,
        threshold_score=recipe.threshold_score,
        threshold_hits=recipe.threshold_hits,
    )
