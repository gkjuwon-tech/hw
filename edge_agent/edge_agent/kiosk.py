"""On-device kiosk HTTP server.

The Tactile Edge appliance ships with an integrated 7" touch display.
At boot, the ``conet-edge-kiosk.service`` systemd unit launches Chromium
in full-screen kiosk mode against this HTTP server (loopback by default).
That is what the operator interacts with on the line — no laptop, no
.exe, no .dmg.

The server is intentionally minimal: a single ``http.server``-based
async wrapper that serves a static bundle out of ``kiosk_static_dir``
and exposes a tiny JSON status endpoint at ``/kiosk/status`` so the
front-end can render live "appliance ok / scanner ok / inference latency"
chips without round-tripping to the cloud.

If the on-disk bundle is missing (e.g. during a partial install) the
server serves a minimal HTML splash inline so the kiosk never shows a
"Site can't be reached" page on boot.
"""

from __future__ import annotations

import asyncio
import json
import logging
import mimetypes
from dataclasses import dataclass
from pathlib import Path

from edge_agent.config import EdgeSettings

logger = logging.getLogger("conet.edge.kiosk")


_INLINE_SPLASH = """<!doctype html>
<html lang="ko-KR">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Conet Tactile \N{EM DASH} Appliance</title>
  <style>
    html, body { margin: 0; padding: 0; height: 100%; background: #0b0c0a; color: #f4f3ee; font-family: -apple-system, "Inter", "Segoe UI", sans-serif; }
    body { display: flex; align-items: center; justify-content: center; }
    main { text-align: center; padding: 2rem; }
    h1 { font-size: 2.2rem; margin: 0 0 .5rem; letter-spacing: .02em; }
    p  { margin: .5rem 0; opacity: .7; }
    .dot { display: inline-block; width: .55rem; height: .55rem; border-radius: 50%; background: #6ad17a; margin-right: .4rem; vertical-align: middle; }
    code { background: #1a1b18; padding: .15rem .35rem; border-radius: .25rem; }
  </style>
</head>
<body>
  <main>
    <h1><span class="dot"></span>Conet Tactile</h1>
    <p>The appliance is starting up. This kiosk is served by the local
       <code>edge_agent</code> on this box \N{EM DASH} no laptop required.</p>
    <p>If this screen stays visible for more than thirty seconds, check
       the <code>conet-edge-agent.service</code> journal.</p>
  </main>
</body>
</html>
""".encode("utf-8")


@dataclass
class KioskStatus:
    """Snapshot of the live agent state, serialized to the kiosk."""

    agent_version: str
    edge_id: str
    line_id: str
    fps: float
    frames_total: int
    frames_dropped: int
    inference_p50_ms: float
    inference_p99_ms: float
    last_verdict: str
    last_score: float
    scanner_port: str


class KioskServer:
    """Tiny asyncio HTTP server that powers the on-device Chromium kiosk.

    The server is deliberately implemented with the stdlib so the
    appliance image doesn't have to ship a second ASGI runtime alongside
    the FastAPI-shaped cloud — ``edge_agent`` is meant to be the *small*
    half of the system.
    """

    def __init__(self, settings: EdgeSettings, status_provider=None) -> None:
        self._settings = settings
        self._status_provider = status_provider
        self._server: asyncio.base_events.Server | None = None
        self._static_dir: Path = settings.kiosk_static_dir

    @property
    def static_dir(self) -> Path:
        return self._static_dir

    async def start(self) -> None:
        if not self._settings.kiosk_enabled:
            logger.info("kiosk.disabled_by_config")
            return
        self._server = await asyncio.start_server(
            self._handle_client,
            host=self._settings.kiosk_host,
            port=self._settings.kiosk_port,
            reuse_address=True,
        )
        logger.info(
            "kiosk.listening",
            extra={
                "host": self._settings.kiosk_host,
                "port": self._settings.kiosk_port,
                "static_dir": str(self._static_dir),
            },
        )

    async def stop(self) -> None:
        if self._server is None:
            return
        self._server.close()
        await self._server.wait_closed()
        self._server = None

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        try:
            request_line = await reader.readline()
            if not request_line:
                return
            try:
                method, target, _ = request_line.decode("ascii", "ignore").split(" ", 2)
            except ValueError:
                self._write_simple(writer, 400, b"bad request")
                return
            # Drain the rest of the headers — we don't use them.
            while True:
                line = await reader.readline()
                if not line or line in (b"\r\n", b"\n"):
                    break

            if method.upper() not in {"GET", "HEAD"}:
                self._write_simple(writer, 405, b"method not allowed")
                return

            path = target.split("?", 1)[0]
            if path in ("/", "/kiosk", "/kiosk/"):
                path = "/kiosk/index.html"

            if path == "/kiosk/status":
                self._write_status(writer)
                return

            self._write_static(writer, path)
        except Exception as exc:  # noqa: BLE001
            logger.warning("kiosk.handler_failed", extra={"err": str(exc)})
        finally:
            try:
                await writer.drain()
            except Exception:  # noqa: BLE001
                pass
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:  # noqa: BLE001
                pass

    # ── responses ──

    def _write_status(self, writer: asyncio.StreamWriter) -> None:
        snap = self._build_status()
        body = json.dumps(
            {
                "agent_version": snap.agent_version,
                "edge_id": snap.edge_id,
                "line_id": snap.line_id,
                "fps": snap.fps,
                "frames_total": snap.frames_total,
                "frames_dropped": snap.frames_dropped,
                "inference_p50_ms": snap.inference_p50_ms,
                "inference_p99_ms": snap.inference_p99_ms,
                "last_verdict": snap.last_verdict,
                "last_score": snap.last_score,
                "scanner_port": snap.scanner_port,
            }
        ).encode("utf-8")
        self._write_response(writer, 200, body, content_type="application/json")

    def _write_static(self, writer: asyncio.StreamWriter, path: str) -> None:
        rel = path.lstrip("/")
        # Strip the ``kiosk/`` prefix so the bundle can be flat on disk;
        # both ``kiosk/index.html`` and ``index.html`` resolve to the
        # same file when ``kiosk_static_dir=/opt/conet/edge_agent/kiosk``.
        if rel.startswith("kiosk/"):
            rel = rel[len("kiosk/") :]
        if not rel:
            rel = "index.html"
        candidate = (self._static_dir / rel).resolve()
        if not str(candidate).startswith(str(self._static_dir.resolve())):
            self._write_simple(writer, 403, b"forbidden")
            return
        if candidate.is_dir():
            candidate = candidate / "index.html"
        if not candidate.is_file():
            if rel in ("index.html", "kiosk/index.html"):
                self._write_response(
                    writer,
                    200,
                    _INLINE_SPLASH,
                    content_type="text/html; charset=utf-8",
                )
                return
            self._write_simple(writer, 404, b"not found")
            return
        body = candidate.read_bytes()
        ctype = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
        if ctype.startswith("text/") and "charset" not in ctype:
            ctype = ctype + "; charset=utf-8"
        if candidate.name == "index.html" and ctype.startswith("text/html"):
            body = self._inject_runtime_config(body)
        self._write_response(writer, 200, body, content_type=ctype)

    @staticmethod
    def _is_loopback(host: str) -> bool:
        return host in {"127.0.0.1", "localhost", "::1"}

    def _inject_runtime_config(self, html: bytes) -> bytes:
        """Inject the control-plane base URL + box identity into index.html.

        The restored operator bundle reads these globals
        (``window.__CONET_API_BASE__`` …) instead of an Electron bridge, so
        the very same static build runs on the appliance and under
        ``vite dev``. The API token is injected **only** when the kiosk is
        bound to loopback, so a box deliberately exposed on a LAN
        (``kiosk_host=0.0.0.0``) never leaks its key into served HTML.
        """
        s = self._settings
        cfg: dict[str, str] = {
            "__CONET_API_BASE__": s.cloud_url,
            "__CONET_EDGE_ID__": s.edge_id,
            "__CONET_LINE_ID__": s.line_id,
        }
        if self._is_loopback(s.kiosk_host) and s.api_key:
            cfg["__CONET_API_TOKEN__"] = s.api_key
        assigns = "".join(f"window.{k}={json.dumps(v)};" for k, v in cfg.items())
        script = (
            "<script>/* injected by edge_agent kiosk server */" + assigns + "</script>"
        ).encode("utf-8")
        marker = b"</head>"
        idx = html.find(marker)
        if idx != -1:
            return html[:idx] + script + html[idx:]
        return script + html

    def _write_simple(
        self, writer: asyncio.StreamWriter, status: int, body: bytes
    ) -> None:
        self._write_response(writer, status, body, content_type="text/plain; charset=utf-8")

    def _write_response(
        self,
        writer: asyncio.StreamWriter,
        status: int,
        body: bytes,
        *,
        content_type: str,
    ) -> None:
        reason = {
            200: "OK",
            400: "Bad Request",
            403: "Forbidden",
            404: "Not Found",
            405: "Method Not Allowed",
        }.get(status, "OK")
        headers = (
            f"HTTP/1.1 {status} {reason}\r\n"
            f"Content-Type: {content_type}\r\n"
            f"Content-Length: {len(body)}\r\n"
            "Cache-Control: no-store\r\n"
            "X-Content-Type-Options: nosniff\r\n"
            "Connection: close\r\n"
            "\r\n"
        ).encode("ascii")
        writer.write(headers)
        writer.write(body)

    # ── status ──

    def _build_status(self) -> KioskStatus:
        from edge_agent import __version__

        provider = self._status_provider
        snap = provider() if callable(provider) else None
        if snap is None:
            return KioskStatus(
                agent_version=__version__,
                edge_id=self._settings.edge_id,
                line_id=self._settings.line_id,
                fps=0.0,
                frames_total=0,
                frames_dropped=0,
                inference_p50_ms=0.0,
                inference_p99_ms=0.0,
                last_verdict="—",
                last_score=0.0,
                scanner_port=self._settings.scanner_port,
            )
        return snap
