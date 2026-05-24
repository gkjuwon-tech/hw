"""Line CRUD."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import Line, get_session
from app.schemas import LineCreate, LineOut

router = APIRouter(prefix="/v1/lines", tags=["lines"])


@router.post("", response_model=LineOut, status_code=status.HTTP_201_CREATED)
async def create_line(
    payload: LineCreate, session: AsyncSession = Depends(get_session)
) -> Line:
    line = Line(
        id=payload.id,
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
async def list_lines(session: AsyncSession = Depends(get_session)) -> list[Line]:
    result = await session.execute(select(Line).order_by(Line.created_at.desc()))
    return list(result.scalars().all())


@router.get("/{line_id}", response_model=LineOut)
async def get_line(
    line_id: str, session: AsyncSession = Depends(get_session)
) -> Line:
    line = await session.get(Line, line_id)
    if line is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "line not found")
    return line
