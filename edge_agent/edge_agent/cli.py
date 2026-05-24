"""Operator CLI: ``conet-edge-agent run`` / ``... status`` / ``... selftest``."""

from __future__ import annotations

import asyncio
import json
import logging

import typer

from edge_agent import __version__
from edge_agent.agent import run_agent
from edge_agent.config import get_settings
from edge_agent.telemetry import read_serial_number, sample_tegrastats

app = typer.Typer(no_args_is_help=True, add_completion=False)


def _setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s %(levelname)-5s %(name)s %(message)s",
    )


@app.command()
def run(log_level: str = "INFO") -> None:
    """Start the on-device agent. This is the systemd entrypoint."""
    _setup_logging(log_level)
    settings = get_settings()
    asyncio.run(run_agent(settings))


@app.command()
def status() -> None:
    """Print the local configuration + a one-shot tegrastats snapshot."""
    _setup_logging("WARNING")
    settings = get_settings()
    snap = sample_tegrastats()
    body = {
        "agent_version": __version__,
        "edge_id": settings.edge_id,
        "line_id": settings.line_id,
        "cloud_url": settings.cloud_url,
        "scanner_port": settings.scanner_port,
        "scan_rate_hz": settings.scan_rate_hz,
        "serial": settings.serial or read_serial_number(),
        "tegrastats": {
            "cpu_pct": snap.cpu_pct,
            "gpu_pct": snap.gpu_pct,
            "cpu_temp_c": snap.cpu_temp_c,
            "gpu_temp_c": snap.gpu_temp_c,
            "ram_used_mb": snap.ram_used_mb,
            "ram_total_mb": snap.ram_total_mb,
            "power_mw": snap.power_mw,
        },
    }
    typer.echo(json.dumps(body, indent=2, default=str))


@app.command()
def version() -> None:
    """Print the agent version."""
    typer.echo(__version__)


if __name__ == "__main__":
    app()
