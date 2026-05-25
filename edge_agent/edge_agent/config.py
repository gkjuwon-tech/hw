"""Edge agent configuration.

All settings come from environment variables (prefix ``CONET_EDGE_``). Defaults
are tuned for a one-line bench rig (200 Hz scanner on /dev/ttyACM0). Production
deployments override every field via the systemd `Environment=` file.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class EdgeSettings(BaseSettings):
    """Process-wide settings for the on-device agent."""

    model_config = SettingsConfigDict(
        env_prefix="CONET_EDGE_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── identity ──
    cloud_url: str = Field(
        default="http://127.0.0.1:8000",
        description="Base URL of the Tactile Cloud control plane.",
    )
    api_key: str = Field(
        default="",
        description=(
            "Tactile Cloud API key. Must be a write-scope token; the agent "
            "calls /v1/lines/.../inspect and /v1/edges/.../heartbeat."
        ),
    )
    edge_id: str = Field(
        default="edge-dev",
        min_length=1,
        max_length=64,
        description="Stable identifier for this Edge box. Used as the edges.id PK.",
    )
    hostname: str = Field(default="", max_length=120)
    serial: str = Field(default="", max_length=64)
    site: str = Field(default="", max_length=120)
    model: str = Field(default="jetson-orin-nano-8gb", max_length=80)

    # ── line binding ──
    line_id: str = Field(
        default="line-dev",
        min_length=1,
        max_length=64,
        description="The conveyor line this edge inspects. One edge → one line in v0.1.",
    )

    # ── scanner ──
    scanner_port: str = Field(
        default="/dev/ttyACM0",
        description="USB-CDC device exposed by the TS-G4 / ESP32-S3 scanner MCU.",
    )
    scanner_baud: int = Field(default=921_600, ge=9_600, le=12_000_000)
    scanner_rows: int = Field(default=16, gt=0, le=512)
    scanner_cols: int = Field(default=16, gt=0, le=512)
    scan_rate_hz: float = Field(default=200.0, gt=0.0, le=2_000.0)
    """Inspection cadence. The MCU runs at up to 1 kHz; we decimate."""

    # ── inference / inspect ──
    inspect_include_heatmap: bool = Field(
        default=True,
        description=(
            "If True, request the cloud to echo the per-cell anomaly heatmap "
            "so the on-device kiosk's live mesh view has something to render. "
            "Set False if you only need pass/fail."
        ),
    )

    # ── on-device kiosk (Chromium full-screen UI) ──
    kiosk_enabled: bool = Field(
        default=True,
        description=(
            "Serve the on-device kiosk HTTP endpoint at "
            "``http://127.0.0.1:{kiosk_port}/`` so the systemd "
            "``conet-edge-kiosk.service`` Chromium can render the operator UI "
            "without any cloud connectivity. Disable on headless / fleet-only "
            "deployments where no display is attached."
        ),
    )
    kiosk_host: str = Field(
        default="127.0.0.1",
        description=(
            "Bind address for the kiosk HTTP server. Defaults to loopback so "
            "the kiosk is never exposed off-box. Override to ``0.0.0.0`` only "
            "if you also put a firewall in front of the appliance."
        ),
    )
    kiosk_port: int = Field(default=8088, ge=1, le=65535)
    kiosk_static_dir: Path = Field(
        default=Path("/opt/conet/edge_agent/kiosk"),
        description=(
            "Directory the kiosk HTTP server serves static files from. "
            "Defaults to the system install path; override during local "
            "development to point at the source tree."
        ),
    )
    kiosk_default_locale: str = Field(default="ko-KR", min_length=2, max_length=10)

    # ── heartbeat / telemetry ──
    heartbeat_period_s: float = Field(default=2.0, gt=0.0, le=60.0)
    """How often to POST a heartbeat to the cloud."""

    # ── spool / resilience ──
    spool_dir: Path = Field(
        default=Path("/var/lib/conet/edge_agent/spool"),
        description="Local on-disk buffer for frames the cloud has not yet accepted.",
    )
    spool_max_bytes: int = Field(
        default=256 * 1024 * 1024,  # 256 MiB
        ge=1024 * 1024,
        le=10 * 1024 * 1024 * 1024,
    )

    # ── networking ──
    request_timeout_s: float = Field(default=5.0, gt=0.0, le=120.0)
    backoff_initial_s: float = Field(default=0.5, gt=0.0, le=60.0)
    backoff_max_s: float = Field(default=30.0, gt=0.0, le=600.0)

    @field_validator("spool_dir")
    @classmethod
    def _coerce_spool(cls, v: Path | str) -> Path:
        return Path(v)


@lru_cache(maxsize=1)
def get_settings() -> EdgeSettings:
    return EdgeSettings()


def reload_settings() -> EdgeSettings:
    get_settings.cache_clear()
    return get_settings()
