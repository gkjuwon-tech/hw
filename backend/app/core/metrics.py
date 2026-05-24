"""Prometheus metrics for the inspection pipeline.

A single ``CollectorRegistry`` is reused for the whole process so we don't
double-register on uvicorn reloads.
"""

from __future__ import annotations

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    Counter,
    Gauge,
    Histogram,
    generate_latest,
)

registry = CollectorRegistry(auto_describe=True)

http_requests_total = Counter(
    "conet_http_requests_total",
    "HTTP requests served, by route, method, and status class.",
    labelnames=("method", "route", "status"),
    registry=registry,
)

http_request_seconds = Histogram(
    "conet_http_request_seconds",
    "HTTP request duration in seconds.",
    labelnames=("method", "route"),
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    registry=registry,
)

inspections_total = Counter(
    "conet_inspections_total",
    "Inspections scored.",
    labelnames=("org_id", "line_id", "verdict"),
    registry=registry,
)

inspection_score = Histogram(
    "conet_inspection_score",
    "Anomaly score distribution.",
    labelnames=("org_id", "line_id"),
    buckets=(0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0, 8.0, 12.0, 20.0),
    registry=registry,
)

inspection_latency_seconds = Histogram(
    "conet_inspection_latency_seconds",
    "Anomaly scoring latency (server-side, excluding I/O).",
    labelnames=("line_id",),
    buckets=(0.001, 0.0025, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5),
    registry=registry,
)

drift_z_gauge = Gauge(
    "conet_line_drift_z",
    "Rolling drift z-score per line (positive = drifting upward).",
    labelnames=("org_id", "line_id"),
    registry=registry,
)

webhook_deliveries_total = Counter(
    "conet_webhook_deliveries_total",
    "Webhook delivery attempts by outcome.",
    labelnames=("status",),
    registry=registry,
)

rate_limit_rejections_total = Counter(
    "conet_rate_limit_rejections_total",
    "Requests rejected by the API rate limiter.",
    labelnames=("scope",),
    registry=registry,
)


def render() -> tuple[bytes, str]:
    """Return ``(payload, content_type)`` for the metrics endpoint."""
    return generate_latest(registry), CONTENT_TYPE_LATEST
