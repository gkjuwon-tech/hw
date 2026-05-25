"""Mesh network fabric — edge-to-edge gossip topology + health monitoring.

Edges on the same LAN discover each other via a periodic gossip tick.
The cloud maintains the authoritative topology graph and provides failover
routing: if one Edge dies, its assigned Lines can be reassigned to a peer
Edge that has spare capacity.

Endpoints:

  ``POST   /v1/mesh/announce``           — edge heartbeat into the mesh fabric
  ``GET    /v1/mesh/topology``           — full mesh graph for the operator UI
  ``POST   /v1/mesh/failover``           — trigger manual failover of a line
  ``GET    /v1/mesh/peers/{edge_id}``    — list reachable peers from an edge
"""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import AuthContext, require_org, require_write_scope
from app.db import Edge, get_session

router = APIRouter(prefix="/v1/mesh", tags=["mesh-network"])

# In-memory mesh topology (production would use Redis or a persistent store)
_topology: dict[str, MeshPeerState] = {}


class MeshPeerState:
    """Runtime state of one edge in the mesh fabric."""

    def __init__(self, edge_id: str, org_id: str, ip: str, port: int) -> None:
        self.edge_id = edge_id
        self.org_id = org_id
        self.ip = ip
        self.port = port
        self.peers: list[str] = []
        self.last_announce: float = time.time()
        self.capacity_free_pct: float = 100.0
        self.latency_ms: dict[str, float] = {}

    def is_alive(self, timeout_s: float = 30.0) -> bool:
        return (time.time() - self.last_announce) < timeout_s


# ── schemas ──────────────────────────────────────────────────────────


class MeshAnnounce(BaseModel):
    edge_id: str = Field(min_length=1, max_length=64)
    ip: str = Field(min_length=7, max_length=45)
    port: int = Field(default=9100, ge=1024, le=65535)
    peers: list[str] = Field(default_factory=list, max_length=64)
    capacity_free_pct: float = Field(default=100.0, ge=0.0, le=100.0)
    latency_to_peers_ms: dict[str, float] = Field(default_factory=dict)


class MeshPeerOut(BaseModel):
    edge_id: str
    ip: str
    port: int
    alive: bool
    capacity_free_pct: float
    last_announce_ago_s: float
    latency_ms: dict[str, float]


class MeshTopologyOut(BaseModel):
    nodes: list[MeshPeerOut]
    edges_count: int
    alive_count: int


class FailoverRequest(BaseModel):
    source_edge_id: str = Field(min_length=1, max_length=64)
    target_edge_id: str = Field(min_length=1, max_length=64)
    line_id: str = Field(min_length=1, max_length=64)


class FailoverResponse(BaseModel):
    status: str
    line_id: str
    new_edge_id: str
    old_edge_id: str


# ── routes ───────────────────────────────────────────────────────────


@router.post("/announce", status_code=status.HTTP_200_OK)
async def mesh_announce(
    payload: MeshAnnounce,
    auth: AuthContext = Depends(require_write_scope),
    session: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    """Edge announces itself into the mesh fabric.

    Called by edge_agent every gossip_interval_s (default 5s). The cloud
    maintains the authoritative graph and returns a simple ACK.
    """
    edge = await session.get(Edge, payload.edge_id)
    if edge is None or edge.org_id != auth.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "edge not found in org")

    peer_state = _topology.get(payload.edge_id)
    if peer_state is None:
        peer_state = MeshPeerState(
            edge_id=payload.edge_id,
            org_id=auth.org_id,
            ip=payload.ip,
            port=payload.port,
        )
        _topology[payload.edge_id] = peer_state

    peer_state.ip = payload.ip
    peer_state.port = payload.port
    peer_state.peers = payload.peers
    peer_state.capacity_free_pct = payload.capacity_free_pct
    peer_state.latency_ms = payload.latency_to_peers_ms
    peer_state.last_announce = time.time()

    return {"status": "ack", "edge_id": payload.edge_id}


@router.get("/topology", response_model=MeshTopologyOut)
async def get_topology(
    auth: AuthContext = Depends(require_org),
) -> MeshTopologyOut:
    """Return the full mesh topology graph scoped to the authenticated org."""
    nodes: list[MeshPeerOut] = []
    alive = 0
    now = time.time()
    for ps in _topology.values():
        if ps.org_id != auth.org_id:
            continue
        is_alive = ps.is_alive()
        if is_alive:
            alive += 1
        nodes.append(
            MeshPeerOut(
                edge_id=ps.edge_id,
                ip=ps.ip,
                port=ps.port,
                alive=is_alive,
                capacity_free_pct=ps.capacity_free_pct,
                last_announce_ago_s=round(now - ps.last_announce, 1),
                latency_ms=ps.latency_ms,
            )
        )
    return MeshTopologyOut(nodes=nodes, edges_count=len(nodes), alive_count=alive)


@router.get("/peers/{edge_id}", response_model=list[MeshPeerOut])
async def get_peers(
    edge_id: str,
    auth: AuthContext = Depends(require_org),
) -> list[MeshPeerOut]:
    """List reachable peers from a specific edge."""
    ps = _topology.get(edge_id)
    if ps is None or ps.org_id != auth.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "edge not in mesh")

    now = time.time()
    result: list[MeshPeerOut] = []
    for peer_id in ps.peers:
        peer = _topology.get(peer_id)
        if peer is None or peer.org_id != auth.org_id:
            continue
        result.append(
            MeshPeerOut(
                edge_id=peer.edge_id,
                ip=peer.ip,
                port=peer.port,
                alive=peer.is_alive(),
                capacity_free_pct=peer.capacity_free_pct,
                last_announce_ago_s=round(now - peer.last_announce, 1),
                latency_ms=peer.latency_ms,
            )
        )
    return result


@router.post("/failover", response_model=FailoverResponse)
async def trigger_failover(
    payload: FailoverRequest,
    auth: AuthContext = Depends(require_write_scope),
    session: AsyncSession = Depends(get_session),
) -> FailoverResponse:
    """Manually reassign a line from one edge to another (operator action).

    Used when an edge is degraded or physically removed. The target edge
    must be alive in the mesh and have spare capacity.
    """
    from app.db import MeshSegment

    target = _topology.get(payload.target_edge_id)
    if target is None or target.org_id != auth.org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "target edge not in mesh")
    if not target.is_alive():
        raise HTTPException(status.HTTP_409_CONFLICT, "target edge is not alive")
    if target.capacity_free_pct < 10.0:
        raise HTTPException(status.HTTP_409_CONFLICT, "target edge has insufficient capacity")

    # Update the mesh segment assignment
    result = await session.execute(
        select(MeshSegment).where(
            MeshSegment.line_id == payload.line_id,
            MeshSegment.edge_id == payload.source_edge_id,
            MeshSegment.org_id == auth.org_id,
        )
    )
    segment = result.scalars().first()
    if segment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no mesh segment found for line on source edge")

    segment.edge_id = payload.target_edge_id
    await session.commit()

    return FailoverResponse(
        status="failover_complete",
        line_id=payload.line_id,
        new_edge_id=payload.target_edge_id,
        old_edge_id=payload.source_edge_id,
    )
