"""edge: integrated touch display columns

Revision ID: 0002_edge_display
Revises: 0001_initial
Create Date: 2026-05-25 00:00:00

The ``edges`` table gained four columns when we moved the operator UI off
the laptop and onto an integrated touch display attached to the box:

* ``display_kind`` — model identifier for the integrated display
* ``display_resolution`` — pixel resolution ``WxH``
* ``display_active`` — kiosk currently rendering?
* ``display_touch_events_per_min`` — kiosk activity level

The ``edges`` table itself was originally created by ``Base.metadata.create_all``
rather than an explicit migration, so this revision is a no-op against a
fresh database; it only runs to bring an upgraded prod database in line.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0002_edge_display"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_edges_table(bind: sa.engine.Connection) -> bool:
    inspector = sa.inspect(bind)
    return "edges" in inspector.get_table_names()


def _column_exists(bind: sa.engine.Connection, table: str, column: str) -> bool:
    inspector = sa.inspect(bind)
    return any(c["name"] == column for c in inspector.get_columns(table))


def upgrade() -> None:
    bind = op.get_bind()
    if not _has_edges_table(bind):
        # Fresh database — ``Base.metadata.create_all`` will create the
        # columns at startup. Skip the explicit ALTERs to avoid a
        # "no such table" error against SQLite.
        return

    if not _column_exists(bind, "edges", "display_kind"):
        op.add_column(
            "edges",
            sa.Column(
                "display_kind",
                sa.String(40),
                nullable=False,
                server_default="hdmi-touch-7in",
            ),
        )
    if not _column_exists(bind, "edges", "display_resolution"):
        op.add_column(
            "edges",
            sa.Column(
                "display_resolution",
                sa.String(20),
                nullable=False,
                server_default="1024x600",
            ),
        )
    if not _column_exists(bind, "edges", "display_active"):
        op.add_column(
            "edges",
            sa.Column(
                "display_active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("0"),
            ),
        )
    if not _column_exists(bind, "edges", "display_touch_events_per_min"):
        op.add_column(
            "edges",
            sa.Column(
                "display_touch_events_per_min",
                sa.Float(),
                nullable=False,
                server_default="0",
            ),
        )


def downgrade() -> None:
    bind = op.get_bind()
    if not _has_edges_table(bind):
        return
    for col in (
        "display_touch_events_per_min",
        "display_active",
        "display_resolution",
        "display_kind",
    ):
        if _column_exists(bind, "edges", col):
            op.drop_column("edges", col)
