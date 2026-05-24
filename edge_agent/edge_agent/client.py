"""Async HTTP client for the Tactile Cloud control plane.

Thin wrapper around ``httpx.AsyncClient`` that:

- Injects the operator's API key as ``Authorization: Bearer ...``.
- Retries on connection errors with capped exponential backoff.
- Centralizes the (small) set of endpoints the agent calls, so the rest of
  the package only depends on this module's surface.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger("conet.edge.client")


@dataclass
class CloudConfig:
    base_url: str
    api_key: str
    timeout_s: float = 5.0
    backoff_initial_s: float = 0.5
    backoff_max_s: float = 30.0


class CloudClient:
    """Async client. Holds an open httpx connection pool."""

    def __init__(self, cfg: CloudConfig) -> None:
        self._cfg = cfg
        self._http = httpx.AsyncClient(
            base_url=cfg.base_url.rstrip("/"),
            timeout=cfg.timeout_s,
            headers=self._auth_headers(),
        )

    def _auth_headers(self) -> dict[str, str]:
        if not self._cfg.api_key:
            return {"accept": "application/json"}
        return {
            "accept": "application/json",
            "authorization": f"Bearer {self._cfg.api_key}",
        }

    async def close(self) -> None:
        await self._http.aclose()

    async def __aenter__(self) -> CloudClient:
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()

    async def _request(
        self, method: str, path: str, json: dict[str, Any] | None = None
    ) -> httpx.Response:
        backoff = self._cfg.backoff_initial_s
        last_exc: Exception | None = None
        for _ in range(6):
            try:
                res = await self._http.request(method, path, json=json)
                return res
            except (httpx.ConnectError, httpx.ReadError, httpx.PoolTimeout) as exc:
                last_exc = exc
                logger.warning(
                    "cloud.request_failed",
                    extra={"method": method, "path": path, "err": str(exc)},
                )
                await asyncio.sleep(backoff)
                backoff = min(self._cfg.backoff_max_s, backoff * 2)
        assert last_exc is not None
        raise last_exc

    # ── enrollment ──

    async def enroll_edge(
        self,
        *,
        edge_id: str,
        hostname: str,
        serial: str,
        model: str,
        site: str,
    ) -> None:
        """Idempotent: POST /v1/edges, ignore 409 if the edge is already enrolled."""
        res = await self._request(
            "POST",
            "/v1/edges",
            json={
                "id": edge_id,
                "hostname": hostname,
                "serial": serial,
                "model": model,
                "site": site,
            },
        )
        if res.status_code in (200, 201):
            return
        if res.status_code == 409:
            logger.info("edge.already_enrolled", extra={"edge_id": edge_id})
            return
        res.raise_for_status()

    async def heartbeat(self, edge_id: str, payload: dict[str, Any]) -> None:
        res = await self._request("POST", f"/v1/edges/{edge_id}/heartbeat", json=payload)
        if res.status_code >= 400:
            logger.warning(
                "heartbeat.bad_status",
                extra={"edge_id": edge_id, "status": res.status_code, "body": res.text[:200]},
            )

    # ── frames / inspect ──

    async def ingest_frame(self, line_id: str, data: list[float]) -> None:
        """Push a frame into the calibration buffer."""
        res = await self._request(
            "POST", f"/v1/lines/{line_id}/frames", json={"data": data}
        )
        if res.status_code >= 400:
            logger.warning(
                "frame.bad_status",
                extra={"line_id": line_id, "status": res.status_code},
            )

    async def inspect(
        self, line_id: str, data: list[float], *, include_heatmap: bool = True
    ) -> dict[str, Any] | None:
        """Score a single frame against the calibrated baseline."""
        path = f"/v1/lines/{line_id}/inspect"
        if include_heatmap:
            path = path + "?include_heatmap=true"
        res = await self._request("POST", path, json={"data": data})
        if res.status_code == 409:
            # Line not calibrated yet — that's an operator-visible state, not
            # an agent error. Drop the frame silently.
            return None
        if res.status_code >= 400:
            logger.warning(
                "inspect.bad_status",
                extra={"line_id": line_id, "status": res.status_code, "body": res.text[:200]},
            )
            return None
        return res.json()
