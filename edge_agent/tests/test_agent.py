"""Supervisor-level test: a fake serial port + a respx-mocked cloud → frames
are inspected and a heartbeat is posted."""

from __future__ import annotations

import asyncio
from typing import Any

import httpx
import numpy as np
import respx

from edge_agent.agent import run_agent
from edge_agent.config import EdgeSettings
from edge_agent.scanner import Frame, encode_frame
from edge_agent.telemetry import TegraSnapshot


class FakeSerial:
    """In-memory serial port that yields preset bytes and then blocks empty."""

    def __init__(self, payload: bytes) -> None:
        self._buf = bytearray(payload)
        self.closed = False

    def read(self, size: int = 1) -> bytes:
        if self.closed:
            return b""
        if not self._buf:
            return b""
        n = min(size, len(self._buf))
        out = bytes(self._buf[:n])
        del self._buf[:n]
        return out

    def close(self) -> None:
        self.closed = True


def _frame_bytes(seq: int = 1) -> bytes:
    rows, cols = 4, 4
    data = (np.arange(rows * cols, dtype=np.uint8) + seq).reshape(rows, cols)
    return encode_frame(Frame(seq=seq, timestamp_us=10 * seq, rows=rows, cols=cols, data=data))


async def test_supervisor_runs_one_cycle() -> None:
    payload = _frame_bytes(1) + _frame_bytes(2)
    port = FakeSerial(payload)

    def open_port(_path: str, _baud: int) -> FakeSerial:
        return port

    snap = TegraSnapshot(
        cpu_pct=11.0,
        gpu_pct=5.0,
        cpu_temp_c=48.0,
        gpu_temp_c=52.0,
        ram_used_mb=2000,
        ram_total_mb=7775,
        power_mw=4200,
    )

    settings = EdgeSettings(
        cloud_url="http://cloud.test",
        api_key="ctk_live_testtest",
        edge_id="edge-supervisor-test",
        line_id="line-test",
        scanner_port="/dev/null",
        heartbeat_period_s=0.05,
    )

    enrolls: list[dict[str, Any]] = []
    heartbeats: list[dict[str, Any]] = []
    inspections: list[dict[str, Any]] = []

    with respx.mock(assert_all_called=False) as mock:
        mock.post("http://cloud.test/v1/edges").mock(
            side_effect=lambda request: _capture(enrolls, request, status=201)
        )
        mock.post(
            f"http://cloud.test/v1/edges/{settings.edge_id}/heartbeat"
        ).mock(side_effect=lambda request: _capture(heartbeats, request, status=200))
        mock.post(f"http://cloud.test/v1/lines/{settings.line_id}/inspect").mock(
            side_effect=lambda request: _capture_inspect(inspections, request)
        )

        stop = asyncio.Event()
        task = asyncio.create_task(
            run_agent(settings, open_port=open_port, sampler=lambda: snap, stop=stop)
        )

        # Wait until both frames are inspected AND at least one heartbeat fires.
        for _ in range(80):
            if len(inspections) >= 2 and len(heartbeats) >= 1:
                break
            await asyncio.sleep(0.05)

        stop.set()
        await asyncio.wait_for(task, timeout=5.0)

    assert len(enrolls) == 1
    assert len(inspections) >= 2
    assert len(heartbeats) >= 1

    hb = heartbeats[-1]
    assert hb["cpu_pct"] == 11.0
    assert hb["gpu_temp_c"] == 52.0
    assert hb["frames_per_second"] >= 0.0


def _capture(
    sink: list[dict[str, Any]], request: httpx.Request, *, status: int
) -> httpx.Response:
    if request.content:
        import json

        sink.append(json.loads(request.content.decode("utf-8")))
    else:
        sink.append({})
    return httpx.Response(status_code=status, json={"ok": True})


def _capture_inspect(
    sink: list[dict[str, Any]], request: httpx.Request
) -> httpx.Response:
    import json

    sink.append(json.loads(request.content.decode("utf-8")))
    return httpx.Response(
        status_code=200,
        json={
            "line_id": "line-test",
            "score": 0.1,
            "hits": 0,
            "cell_score_max": 0.0,
            "verdict": "pass",
            "drift_z": 0.0,
            "features": {},
            "heatmap": None,
        },
    )
