"""Installed mesh segment inventory.

A *MeshSegment* is a single piece cut from a Tactile Mesh roll and physically
installed on a production line. We track it as a first-class resource so the
operator can: ask "which lot is on line 7?", drive lifetime/wear accounting,
and reconcile dead-cell maps against the roll's QA history.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import AuthContext, require_org, require_write_scope
from app.db import Edge, Line, MeshSegment, get_session
from app.schemas import MeshSegmentCreate, MeshSegmentOut, MeshSegmentUpdate

router = APIRouter(prefix="/v1/meshes", tags=["meshes"])


@router.post("", response_model=MeshSegmentOut, status_code=status.HTTP_201_CREATED)
async def install_mesh(
    payload: MeshSegmentCreate,
    auth: AuthContext = Depends(require_write_scope),
    session: AsyncSession = Depends(get_session),
) -> MeshSegment:
    line = await session.get(Line, payload.line_id)
    if line is None or line.org_id != auth.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "line not found")
    if payload.edge_id:
        edge = await session.get(Edge, payload.edge_id)
        if edge is None or edge.org_id != auth.org_id:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "edge not found")

    segment = MeshSegment(
        id=payload.id,
        org_id=auth.org_id,
        line_id=payload.line_id,
        edge_id=payload.edge_id,
        roll_lot=payload.roll_lot,
        belt_width_mm=payload.belt_width_mm,
        length_mm=payload.length_mm,
        rows=payload.rows,
        cols=payload.cols,
        expected_lifetime_days=payload.expected_lifetime_days,
        notes=payload.notes,
    )
    session.add(segment)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise HTTPException(
            status.HTTP_409_CONFLICT, "mesh segment id already in use"
        ) from exc
    await session.refresh(segment)
    return segment


@router.get("", response_model=list[MeshSegmentOut])
async def list_meshes(
    line_id: str | None = None,
    edge_id: str | None = None,
    auth: AuthContext = Depends(require_org),
    session: AsyncSession = Depends(get_session),
) -> list[MeshSegment]:
    stmt = select(MeshSegment).where(MeshSegment.org_id == auth.org_id)
    if line_id is not None:
        stmt = stmt.where(MeshSegment.line_id == line_id)
    if edge_id is not None:
        stmt = stmt.where(MeshSegment.edge_id == edge_id)
    stmt = stmt.order_by(MeshSegment.installed_at.desc())
    result = await session.execute(stmt)
    return list(result.scalars().all())


@router.get("/{mesh_id}", response_model=MeshSegmentOut)
async def get_mesh(
    mesh_id: str,
    auth: AuthContext = Depends(require_org),
    session: AsyncSession = Depends(get_session),
) -> MeshSegment:
    segment = await session.get(MeshSegment, mesh_id)
    if segment is None or segment.org_id != auth.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "mesh segment not found")
    return segment


@router.patch("/{mesh_id}", response_model=MeshSegmentOut)
async def update_mesh(
    mesh_id: str,
    payload: MeshSegmentUpdate,
    auth: AuthContext = Depends(require_write_scope),
    session: AsyncSession = Depends(get_session),
) -> MeshSegment:
    segment = await session.get(MeshSegment, mesh_id)
    if segment is None or segment.org_id != auth.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "mesh segment not found")
    if payload.edge_id is not None:
        if payload.edge_id == "":
            segment.edge_id = None
        else:
            edge = await session.get(Edge, payload.edge_id)
            if edge is None or edge.org_id != auth.org_id:
                raise HTTPException(status.HTTP_404_NOT_FOUND, "edge not found")
            segment.edge_id = payload.edge_id
    if payload.health_pct is not None:
        segment.health_pct = payload.health_pct
    if payload.dead_cells is not None:
        segment.dead_cells = payload.dead_cells
    if payload.notes is not None:
        segment.notes = payload.notes
    await session.commit()
    await session.refresh(segment)
    return segment


@router.delete("/{mesh_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_mesh(
    mesh_id: str,
    auth: AuthContext = Depends(require_write_scope),
    session: AsyncSession = Depends(get_session),
) -> None:
    segment = await session.get(MeshSegment, mesh_id)
    if segment is None or segment.org_id != auth.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "mesh segment not found")
    await session.delete(segment)
    await session.commit()
