"""Line CRUD scoped to the authenticated organization."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import AuthContext, require_org, require_write_scope
from app.db import Line, get_session
from app.schemas import LineCreate, LineOut, LineUpdate

router = APIRouter(prefix="/v1/lines", tags=["lines"])


@router.post("", response_model=LineOut, status_code=status.HTTP_201_CREATED)
async def create_line(
    payload: LineCreate,
    auth: AuthContext = Depends(require_write_scope),
    session: AsyncSession = Depends(get_session),
) -> Line:
    line = Line(
        id=payload.id,
        org_id=auth.org_id,
        customer_tag=payload.customer_tag,
        rows=payload.rows,
        cols=payload.cols,
    )
    session.add(line)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "line already exists") from exc
    await session.refresh(line)
    return line


@router.get("", response_model=list[LineOut])
async def list_lines(
    auth: AuthContext = Depends(require_org),
    session: AsyncSession = Depends(get_session),
) -> list[Line]:
    result = await session.execute(
        select(Line).where(Line.org_id == auth.org_id).order_by(Line.created_at.desc())
    )
    return list(result.scalars().all())


@router.get("/{line_id}", response_model=LineOut)
async def get_line(
    line_id: str,
    auth: AuthContext = Depends(require_org),
    session: AsyncSession = Depends(get_session),
) -> Line:
    line = await session.get(Line, line_id)
    if line is None or line.org_id != auth.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "line not found")
    return line


@router.patch("/{line_id}", response_model=LineOut)
async def update_line(
    line_id: str,
    payload: LineUpdate,
    auth: AuthContext = Depends(require_write_scope),
    session: AsyncSession = Depends(get_session),
) -> Line:
    line = await session.get(Line, line_id)
    if line is None or line.org_id != auth.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "line not found")
    if payload.customer_tag is not None:
        line.customer_tag = payload.customer_tag
    if payload.threshold_score is not None:
        line.threshold_score = payload.threshold_score
    if payload.threshold_hits is not None:
        line.threshold_hits = payload.threshold_hits
    await session.commit()
    await session.refresh(line)
    return line


@router.delete("/{line_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_line(
    line_id: str,
    auth: AuthContext = Depends(require_write_scope),
    session: AsyncSession = Depends(get_session),
) -> None:
    line = await session.get(Line, line_id)
    if line is None or line.org_id != auth.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "line not found")
    await session.delete(line)
    await session.commit()
