"""Shared fixtures: env isolation + ephemeral spool dirs."""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch) -> Path:
    tmp = Path(tempfile.mkdtemp(prefix="conet-edge-test-"))
    monkeypatch.setenv("CONET_EDGE_CLOUD_URL", "http://cloud.test")
    monkeypatch.setenv("CONET_EDGE_API_KEY", "ctk_live_testtest")
    monkeypatch.setenv("CONET_EDGE_EDGE_ID", "edge-test")
    monkeypatch.setenv("CONET_EDGE_LINE_ID", "line-test")
    monkeypatch.setenv("CONET_EDGE_SCANNER_PORT", "/dev/null")
    monkeypatch.setenv("CONET_EDGE_SPOOL_DIR", str(tmp / "spool"))
    monkeypatch.setenv("CONET_EDGE_HEARTBEAT_PERIOD_S", "0.05")
    # Make sure config cache is fresh.
    for mod in [m for m in list(sys.modules) if m.startswith("edge_agent")]:
        del sys.modules[mod]
    os.environ["PYTHONASYNCIODEBUG"] = "0"
    return tmp
