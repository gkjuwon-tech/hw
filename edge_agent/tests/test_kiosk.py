"""Tests for the on-device kiosk HTTP server."""

from __future__ import annotations

import asyncio
import json
import socket
from pathlib import Path

import pytest

from edge_agent.config import EdgeSettings
from edge_agent.kiosk import KioskServer, KioskStatus


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _make_settings(tmp_path: Path, port: int) -> EdgeSettings:
    return EdgeSettings(
        edge_id="edge-test",
        line_id="line-test",
        scanner_port="/dev/null",
        kiosk_enabled=True,
        kiosk_host="127.0.0.1",
        kiosk_port=port,
        kiosk_static_dir=tmp_path,
    )


async def _fetch(port: int, path: str) -> tuple[int, dict[str, str], bytes]:
    """Minimal HTTP/1.1 client. Avoids pulling in httpx for one test."""
    reader, writer = await asyncio.open_connection("127.0.0.1", port)
    writer.write(
        ("GET " + path + " HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n").encode("ascii")
    )
    await writer.drain()
    raw = await reader.read(65536)
    writer.close()
    try:
        await writer.wait_closed()
    except Exception:
        pass
    head, _, body = raw.partition(b"\r\n\r\n")
    status_line, _, header_block = head.partition(b"\r\n")
    status = int(status_line.split(b" ")[1])
    headers = {}
    for line in header_block.split(b"\r\n"):
        if b":" in line:
            k, _, v = line.partition(b":")
            headers[k.decode("ascii").strip().lower()] = v.decode("ascii").strip()
    return status, headers, body


@pytest.mark.asyncio
async def test_kiosk_server_serves_inline_splash_when_bundle_missing(
    tmp_path: Path,
) -> None:
    port = _free_port()
    server = KioskServer(_make_settings(tmp_path, port))
    await server.start()
    try:
        status, headers, body = await _fetch(port, "/")
        assert status == 200
        assert headers["content-type"].startswith("text/html")
        # The inline splash is served when index.html isn't on disk.
        assert b"Conet Tactile" in body
        assert b"edge_agent" in body
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_kiosk_server_serves_index_from_static_dir(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text(
        "<!doctype html><title>real-kiosk</title>", encoding="utf-8"
    )
    port = _free_port()
    server = KioskServer(_make_settings(tmp_path, port))
    await server.start()
    try:
        status, headers, body = await _fetch(port, "/kiosk/index.html")
        assert status == 200
        assert headers["content-type"].startswith("text/html")
        assert b"real-kiosk" in body
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_kiosk_injects_runtime_config_into_index(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text(
        "<!doctype html><html><head><title>op</title></head>"
        "<body><div id=root></div></body></html>",
        encoding="utf-8",
    )
    port = _free_port()
    settings = EdgeSettings(
        edge_id="edge-test",
        line_id="line-test",
        scanner_port="/dev/null",
        cloud_url="https://cloud.example/api",
        api_key="ctk_live_secret",
        kiosk_enabled=True,
        kiosk_host="127.0.0.1",
        kiosk_port=port,
        kiosk_static_dir=tmp_path,
    )
    server = KioskServer(settings)
    await server.start()
    try:
        status, headers, body = await _fetch(port, "/kiosk/index.html")
        assert status == 200
        assert headers["content-type"].startswith("text/html")
        text = body.decode("utf-8")
        # Base URL + identity are injected before </head>.
        assert 'window.__CONET_API_BASE__="https://cloud.example/api"' in text
        assert 'window.__CONET_EDGE_ID__="edge-test"' in text
        assert text.index("__CONET_API_BASE__") < text.index("</head>")
        # On loopback the box token is injected for the bundle to use.
        assert 'window.__CONET_API_TOKEN__="ctk_live_secret"' in text
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_kiosk_omits_token_when_not_loopback(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text(
        "<!doctype html><html><head></head><body></body></html>",
        encoding="utf-8",
    )
    port = _free_port()
    settings = EdgeSettings(
        edge_id="edge-test",
        line_id="line-test",
        scanner_port="/dev/null",
        cloud_url="https://cloud.example/api",
        api_key="ctk_live_secret",
        kiosk_enabled=True,
        kiosk_host="0.0.0.0",
        kiosk_port=port,
        kiosk_static_dir=tmp_path,
    )
    server = KioskServer(settings)
    await server.start()
    try:
        _status, _headers, body = await _fetch(port, "/kiosk/index.html")
        text = body.decode("utf-8")
        # Base URL is fine to expose; the secret token must NOT leak when
        # the kiosk is bound to a non-loopback address.
        assert "__CONET_API_BASE__" in text
        assert "ctk_live_secret" not in text
        assert "__CONET_API_TOKEN__" not in text
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_kiosk_server_status_endpoint_returns_json(tmp_path: Path) -> None:
    port = _free_port()
    sentinel = KioskStatus(
        agent_version="0.0.1-test",
        edge_id="edge-test",
        line_id="line-test",
        fps=42.0,
        frames_total=7,
        frames_dropped=1,
        inference_p50_ms=2.5,
        inference_p99_ms=9.0,
        last_verdict="pass",
        last_score=0.123,
        scanner_port="/dev/null",
    )
    server = KioskServer(_make_settings(tmp_path, port), status_provider=lambda: sentinel)
    await server.start()
    try:
        status, headers, body = await _fetch(port, "/kiosk/status")
        assert status == 200
        assert headers["content-type"].startswith("application/json")
        payload = json.loads(body)
        assert payload["edge_id"] == "edge-test"
        assert payload["line_id"] == "line-test"
        assert payload["fps"] == 42.0
        assert payload["frames_total"] == 7
        assert payload["last_verdict"] == "pass"
    finally:
        await server.stop()


@pytest.mark.asyncio
async def test_kiosk_server_rejects_path_traversal(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("ok", encoding="utf-8")
    port = _free_port()
    server = KioskServer(_make_settings(tmp_path, port))
    await server.start()
    try:
        status, _headers, _body = await _fetch(port, "/kiosk/../../../etc/passwd")
        # The resolved path either falls inside ``tmp_path`` (404) or
        # outside it (403) — both are fine; the only forbidden outcome
        # is leaking /etc/passwd, which would have a real-looking shape.
        assert status in (403, 404)
    finally:
        await server.stop()
