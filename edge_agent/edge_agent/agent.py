"""Main daemon loop.

Three concurrent coroutines:

  ``scanner_loop``    — read the USB-CDC port, decode ``frame_t`` records,
                        push frames onto a bounded asyncio.Queue.
  ``inference_loop``  — pull frames off the queue, call /v1/lines/.../inspect,
                        record p50/p99 latency.
  ``heartbeat_loop``  — sample tegrastats every ``heartbeat_period_s`` and
                        POST /v1/edges/{id}/heartbeat with the metrics +
                        the latest inference latency percentiles.

All three are supervised by :func:`run_agent`, which gives each loop the
same cancel/restart semantics and a single shutdown signal.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections import deque
from collections.abc import Awaitable, Callable

from edge_agent import __version__
from edge_agent.client import CloudClient
from edge_agent.config import EdgeSettings
from edge_agent.scanner import Frame, FrameReader, SerialLike
from edge_agent.telemetry import (
    TegraSnapshot,
    read_serial_number,
    sample_tegrastats,
)

logger = logging.getLogger("conet.edge.agent")

# Bounded queue between scanner_loop and inference_loop. If inference can't
# keep up, the scanner drops *oldest* — we'd rather inspect a recent frame
# than a stale one. Sized so a half-second backlog at 200 Hz is tolerable.
_FRAME_QUEUE_CAPACITY = 128


class LatencyTracker:
    """Tiny p50/p99 estimator over a rolling window. Pure stdlib."""

    def __init__(self, window: int = 256) -> None:
        self._samples: deque[float] = deque(maxlen=window)

    def observe(self, ms: float) -> None:
        self._samples.append(ms)

    def percentiles(self) -> tuple[float, float]:
        if not self._samples:
            return (0.0, 0.0)
        snap = sorted(self._samples)
        p50 = snap[len(snap) // 2]
        p99_idx = max(0, int(len(snap) * 0.99) - 1)
        p99 = snap[p99_idx]
        return (float(p50), float(p99))


class FrameRateMeter:
    """1-second sliding window frame rate. Used in heartbeats + status bar."""

    def __init__(self, window_s: float = 1.0) -> None:
        self._window_s = window_s
        self._stamps: deque[float] = deque()

    def tick(self) -> None:
        now = time.monotonic()
        self._stamps.append(now)
        cutoff = now - self._window_s
        while self._stamps and self._stamps[0] < cutoff:
            self._stamps.popleft()

    @property
    def fps(self) -> float:
        if not self._stamps:
            return 0.0
        return len(self._stamps) / self._window_s


class AgentState:
    """Live runtime state shared across the three loops."""

    def __init__(self) -> None:
        self.inference = LatencyTracker()
        self.fps = FrameRateMeter()
        self.frames_total = 0
        self.frames_dropped = 0
        self.last_verdict: str = "—"
        self.last_score: float = 0.0


# ── loops ──


async def scanner_loop(
    settings: EdgeSettings,
    queue: asyncio.Queue[Frame],
    open_port: Callable[[str, int], SerialLike],
    *,
    state: AgentState,
    stop: asyncio.Event,
) -> None:
    """Read the USB-CDC port forever; reconnect on any failure."""
    reader = FrameReader()
    backoff = settings.backoff_initial_s
    while not stop.is_set():
        try:
            port = open_port(settings.scanner_port, settings.scanner_baud)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "scanner.open_failed",
                extra={"port": settings.scanner_port, "err": str(exc)},
            )
            await _sleep_or_stop(backoff, stop)
            backoff = min(settings.backoff_max_s, backoff * 2)
            continue
        backoff = settings.backoff_initial_s
        try:
            await _read_port_forever(port, reader, queue, state=state, stop=stop)
        except Exception as exc:  # noqa: BLE001
            logger.warning("scanner.read_failed", extra={"err": str(exc)})
        finally:
            try:
                port.close()
            except Exception:  # noqa: BLE001
                pass


async def _read_port_forever(
    port: SerialLike,
    reader: FrameReader,
    queue: asyncio.Queue[Frame],
    *,
    state: AgentState,
    stop: asyncio.Event,
) -> None:
    loop = asyncio.get_running_loop()
    while not stop.is_set():
        # ``port.read(...)`` is blocking; run it in the default executor so
        # the asyncio scheduler keeps running the inference + heartbeat
        # coroutines.
        chunk = await loop.run_in_executor(None, port.read, 4096)
        if not chunk:
            await asyncio.sleep(0.01)
            continue
        for frame in reader.feed(chunk):
            state.frames_total += 1
            state.fps.tick()
            try:
                queue.put_nowait(frame)
            except asyncio.QueueFull:
                # Drop the oldest to keep up with the line.
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                state.frames_dropped += 1
                try:
                    queue.put_nowait(frame)
                except asyncio.QueueFull:
                    state.frames_dropped += 1


async def inference_loop(
    settings: EdgeSettings,
    queue: asyncio.Queue[Frame],
    client: CloudClient,
    *,
    state: AgentState,
    stop: asyncio.Event,
) -> None:
    while not stop.is_set():
        try:
            frame = await asyncio.wait_for(queue.get(), timeout=0.5)
        except asyncio.TimeoutError:
            continue

        t0 = time.perf_counter()
        result = await client.inspect(
            settings.line_id,
            frame.to_list(),
            include_heatmap=settings.inspect_include_heatmap,
        )
        elapsed_ms = (time.perf_counter() - t0) * 1000.0
        state.inference.observe(elapsed_ms)
        if result is not None:
            state.last_verdict = str(result.get("verdict", "—"))
            try:
                state.last_score = float(result.get("score", 0.0))
            except (TypeError, ValueError):
                state.last_score = 0.0


async def heartbeat_loop(
    settings: EdgeSettings,
    client: CloudClient,
    *,
    state: AgentState,
    stop: asyncio.Event,
    sampler: Callable[[], TegraSnapshot] = sample_tegrastats,
    sleep: Callable[[float], Awaitable[None]] | None = None,
) -> None:
    sleeper = sleep or asyncio.sleep
    while not stop.is_set():
        snap = sampler()
        p50, p99 = state.inference.percentiles()
        payload = {
            "firmware_version": "TS-G4 v0.3",
            "agent_version": __version__,
            "cpu_pct": snap.cpu_pct,
            "gpu_pct": snap.gpu_pct,
            "cpu_temp_c": snap.cpu_temp_c,
            "gpu_temp_c": snap.gpu_temp_c,
            "ram_used_mb": snap.ram_used_mb,
            "ram_total_mb": snap.ram_total_mb,
            "power_mw": snap.power_mw,
            "inference_p50_ms": p50,
            "inference_p99_ms": p99,
            "frames_per_second": state.fps.fps,
        }
        try:
            await client.heartbeat(settings.edge_id, payload)
        except Exception as exc:  # noqa: BLE001
            logger.warning("heartbeat.failed", extra={"err": str(exc)})
        await sleeper(settings.heartbeat_period_s)


# ── supervisor ──


async def run_agent(
    settings: EdgeSettings,
    *,
    open_port: Callable[[str, int], SerialLike] | None = None,
    sampler: Callable[[], TegraSnapshot] | None = None,
    stop: asyncio.Event | None = None,
) -> None:
    """Top-level supervisor.

    ``open_port`` / ``sampler`` are injection points for tests: the unit
    tests pass an in-memory fake serial port and a stub tegrastats sampler
    so the supervisor can be exercised without root or hardware.
    """
    if open_port is None:
        from edge_agent.scanner import open_serial

        open_port = open_serial

    stop = stop or asyncio.Event()
    state = AgentState()
    queue: asyncio.Queue[Frame] = asyncio.Queue(maxsize=_FRAME_QUEUE_CAPACITY)

    from edge_agent.client import CloudConfig

    cloud = CloudClient(
        CloudConfig(
            base_url=settings.cloud_url,
            api_key=settings.api_key,
            timeout_s=settings.request_timeout_s,
            backoff_initial_s=settings.backoff_initial_s,
            backoff_max_s=settings.backoff_max_s,
        )
    )

    try:
        await cloud.enroll_edge(
            edge_id=settings.edge_id,
            hostname=settings.hostname or settings.edge_id,
            serial=settings.serial or read_serial_number(),
            model=settings.model,
            site=settings.site,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("edge.enroll_failed", extra={"err": str(exc)})

    sampler = sampler or sample_tegrastats

    tasks: list[asyncio.Task[None]] = [
        asyncio.create_task(
            scanner_loop(settings, queue, open_port, state=state, stop=stop),
            name="scanner_loop",
        ),
        asyncio.create_task(
            inference_loop(settings, queue, cloud, state=state, stop=stop),
            name="inference_loop",
        ),
        asyncio.create_task(
            heartbeat_loop(settings, cloud, state=state, stop=stop, sampler=sampler),
            name="heartbeat_loop",
        ),
    ]
    try:
        # Run until the stop event fires; cancel any task that crashes first.
        done, pending = await asyncio.wait(
            tasks, return_when=asyncio.FIRST_EXCEPTION
        )
        for task in done:
            exc = task.exception()
            if exc is not None:
                logger.error(
                    "agent.task_crashed",
                    extra={"task": task.get_name(), "err": str(exc)},
                )
        stop.set()
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)
    finally:
        await cloud.close()


async def _sleep_or_stop(delay: float, stop: asyncio.Event) -> None:
    try:
        await asyncio.wait_for(stop.wait(), timeout=delay)
    except asyncio.TimeoutError:
        return
