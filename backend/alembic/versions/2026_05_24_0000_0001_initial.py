"""initial schema — organizations, api_keys, lines, inspections, webhooks

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-24 00:00:00
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "organizations",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("contact_email", sa.String(200), nullable=False, server_default=""),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column(
            "rate_limit_per_minute", sa.Integer(), nullable=False, server_default="0"
        ),
    )

    op.create_table(
        "api_keys",
        sa.Column("id", sa.String(48), primary_key=True),
        sa.Column("org_id", sa.String(64), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("label", sa.String(120), nullable=False, server_default=""),
        sa.Column("hashed_secret", sa.String(128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("scope", sa.String(32), nullable=False, server_default="read_write"),
    )
    op.create_index("ix_api_keys_org_id", "api_keys", ["org_id"])

    op.create_table(
        "lines",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("org_id", sa.String(64), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("customer_tag", sa.String(128), nullable=False, server_default=""),
        sa.Column("rows", sa.Integer(), nullable=False),
        sa.Column("cols", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="awaiting_calibration"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("calibrated_at", sa.DateTime(timezone=True)),
        sa.Column("n_samples", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("drift", sa.Float(), nullable=False, server_default="0"),
        sa.Column("drift_z", sa.Float(), nullable=False, server_default="0"),
        sa.Column("threshold_score", sa.Float(), nullable=False, server_default="3.0"),
        sa.Column("threshold_hits", sa.Integer(), nullable=False, server_default="8"),
    )
    op.create_index("ix_lines_org_id", "lines", ["org_id"])

    op.create_table(
        "inspections",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("org_id", sa.String(64), nullable=False),
        sa.Column("line_id", sa.String(64), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("hits", sa.Integer(), nullable=False),
        sa.Column("cell_score_max", sa.Float(), nullable=False, server_default="0"),
        sa.Column("verdict", sa.String(16), nullable=False),
        sa.Column("drift_z", sa.Float(), nullable=False, server_default="0"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index("ix_inspections_org_id", "inspections", ["org_id"])
    op.create_index("ix_inspections_line_id", "inspections", ["line_id"])
    op.create_index("ix_inspections_created_at", "inspections", ["created_at"])
    op.create_index(
        "ix_inspections_line_created", "inspections", ["line_id", "created_at"]
    )

    op.create_table(
        "webhook_endpoints",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("org_id", sa.String(64), sa.ForeignKey("organizations.id"), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("secret", sa.String(96), nullable=False),
        sa.Column(
            "events",
            sa.String(256),
            nullable=False,
            server_default="inspection.failed,drift.alert",
        ),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("description", sa.String(200), nullable=False, server_default=""),
        sa.UniqueConstraint("org_id", "url", name="uq_webhook_org_url"),
    )
    op.create_index("ix_webhook_endpoints_org_id", "webhook_endpoints", ["org_id"])

    op.create_table(
        "webhook_deliveries",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "endpoint_id",
            sa.String(36),
            sa.ForeignKey("webhook_endpoints.id"),
            nullable=False,
        ),
        sa.Column("org_id", sa.String(64), nullable=False),
        sa.Column("event", sa.String(64), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_response_status", sa.Integer()),
        sa.Column("last_error", sa.Text()),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("delivered_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_webhook_deliveries_endpoint_id", "webhook_deliveries", ["endpoint_id"])
    op.create_index("ix_webhook_deliveries_org_id", "webhook_deliveries", ["org_id"])
    op.create_index("ix_webhook_deliveries_status", "webhook_deliveries", ["status"])
    op.create_index("ix_webhook_deliveries_created_at", "webhook_deliveries", ["created_at"])


def downgrade() -> None:
    op.drop_table("webhook_deliveries")
    op.drop_table("webhook_endpoints")
    op.drop_table("inspections")
    op.drop_table("lines")
    op.drop_table("api_keys")
    op.drop_table("organizations")
