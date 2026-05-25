"""Service configuration.

Settings are read from environment variables (``CONET_*``). Defaults are tuned
for local development; production overrides come from the platform (Docker
secrets, Kubernetes config maps, etc.).
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_data_dir() -> Path:
    here = Path(__file__).resolve().parent.parent.parent
    return here / "data"


class Settings(BaseSettings):
    """Process-wide settings.

    Override any field via environment variable, prefix ``CONET_``. Example:
    ``CONET_DATABASE_URL=postgresql+asyncpg://...``.
    """

    model_config = SettingsConfigDict(
        env_prefix="CONET_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ── service identity ────────────────────────────────────────────────
    service_name: str = "conet-tactile-cloud"
    environment: str = Field(default="dev", description="dev | staging | prod")
    log_level: str = Field(default="INFO")
    log_json: bool = Field(default=True, description="Emit logs as JSON (off for local TTY).")

    # ── storage ────────────────────────────────────────────────────────
    database_url: str = "sqlite+aiosqlite:///./conet_tactile.db"
    data_dir: Path = Field(default_factory=_default_data_dir)
    """Directory for on-disk numpy baselines and recent-frame buffers."""

    # ── anomaly detection ──────────────────────────────────────────────
    min_calibration_samples: int = Field(default=5, ge=1, le=64)
    anomaly_sigma_threshold: float = Field(default=3.0, ge=0.5, le=10.0)
    drift_window: int = Field(default=200, ge=10, le=10_000)
    drift_alert_z: float = Field(default=2.5, ge=0.5, le=10.0)
    heatmap_max_cells: int = Field(default=4096, ge=64, le=65_536)

    # ── eventing ───────────────────────────────────────────────────────
    event_buffer_size: int = Field(default=256, ge=1, le=10_000)

    # ── auth / security ────────────────────────────────────────────────
    auth_required: bool = Field(
        default=False,
        description=(
            "If True, every /v1/* request must carry a valid API key. "
            "Defaults to False for local development; production must set True."
        ),
    )
    api_key_prefix: str = Field(default="ctk", min_length=2, max_length=8)
    api_key_secret_pepper: str = Field(
        default="conet-tactile-dev-pepper-change-me",
        description="Server-side pepper mixed into API-key hashes. Rotate in prod.",
        min_length=8,
    )
    bootstrap_admin_token: str | None = Field(
        default=None,
        description=(
            "Static superuser token for /v1/admin/* operations. If unset, admin "
            "endpoints are disabled — use the seed CLI instead."
        ),
    )
    legacy_edge_enroll_enabled: bool = Field(
        default=True,
        description=(
            "If True, POST /v1/edges accepts direct enrollment (back-compat). "
            "Set False in production so operators must use the claim-redeem flow "
            "(POST /v1/claims + POST /v1/claims/redeem) which validates serial "
            "and firmware version of the physical appliance."
        ),
    )

    # ── rate limit ─────────────────────────────────────────────────────
    rate_limit_enabled: bool = True
    rate_limit_default_per_minute: int = Field(default=600, ge=1, le=1_000_000)
    rate_limit_burst: int = Field(default=120, ge=1, le=1_000_000)

    # ── webhooks ───────────────────────────────────────────────────────
    webhook_max_attempts: int = Field(default=8, ge=1, le=32)
    webhook_base_backoff_seconds: float = Field(default=2.0, ge=0.1, le=60.0)
    webhook_max_backoff_seconds: float = Field(default=600.0, ge=1.0, le=86_400.0)
    webhook_request_timeout_seconds: float = Field(default=10.0, ge=0.5, le=120.0)
    webhook_signature_header: str = "X-Conet-Signature"
    webhook_id_header: str = "X-Conet-Webhook-Id"
    webhook_event_header: str = "X-Conet-Event"

    # ── pricing (in KRW; USD derived at quote time) ────────────────────
    pricing_usd_per_krw: float = Field(default=1 / 1360.0, gt=0)

    # ── store / stripe checkout ────────────────────────────────────────
    # Live mode is driven entirely by whether CONET_STRIPE_SECRET_KEY is set:
    #
    #   * key present  → live mode. Real Stripe Checkout Sessions are created
    #     over HTTPS and the marketing site redirects to checkout.stripe.com.
    #     Drop a TEST key (``sk_test_…``) here to exercise the full purchase
    #     journey against Stripe's test environment — test cards only, no
    #     real money moves. Swap to a live key (``sk_live_…``) for production.
    #   * key absent   → mock mode. No Stripe calls are made, a local
    #     pretend-checkout page is served, and the success flow is driven
    #     by the backend. Useful for CI, offline demos, and recorded walkthroughs.
    #
    # Mock mode can also be forced on with CONET_STRIPE_MOCK_MODE=true even
    # when a key is present (e.g. to demo without touching Stripe at all).
    stripe_secret_key: str | None = Field(default=None)
    stripe_publishable_key: str | None = Field(default=None)
    stripe_webhook_secret: str | None = Field(default=None)
    stripe_mock_mode: bool = Field(default=False)
    store_default_currency: str = Field(default="usd", min_length=3, max_length=3)
    store_success_url: str = Field(
        default="http://localhost:5173/product/activate.html",
        description="Where Stripe redirects after the hardware checkout succeeds.",
    )
    store_cancel_url: str = Field(
        default="http://localhost:5173/product/scanner.html",
        description="Where Stripe redirects if the customer abandons checkout.",
    )
    store_software_success_url: str = Field(
        default="http://localhost:5173/product/download.html",
    )
    store_software_cancel_url: str = Field(
        default="http://localhost:5173/product/activate.html",
    )
    store_software_trial_days: int = Field(default=30, ge=0, le=365)
    store_software_monthly_usd: int = Field(default=49, ge=0, le=10_000)
    store_download_url_windows: str = Field(
        default="https://github.com/gkjuwon-tech/hw/actions/workflows/ci.yml",
        description="URL to the latest Windows installer (default: GH Actions artifacts).",
    )
    store_download_url_mac: str = Field(
        default="https://github.com/gkjuwon-tech/hw/actions/workflows/ci.yml",
    )
    store_download_url_linux: str = Field(
        default="https://github.com/gkjuwon-tech/hw/actions/workflows/ci.yml",
    )

    # ── observability ──────────────────────────────────────────────────
    metrics_enabled: bool = True
    cors_origins: list[str] = Field(default_factory=lambda: ["*"])

    @field_validator("data_dir")
    @classmethod
    def _coerce_data_dir(cls, v: Path | str) -> Path:
        return Path(v)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    s = Settings()
    s.data_dir.mkdir(parents=True, exist_ok=True)
    (s.data_dir / "baselines").mkdir(parents=True, exist_ok=True)
    return s


# Module-level alias for backward compatibility with the v0.1 import style.
settings = get_settings()


def reload_settings() -> Settings:
    """Drop the cache and re-read the environment. Used in tests."""
    global settings
    get_settings.cache_clear()
    settings = get_settings()
    return settings
