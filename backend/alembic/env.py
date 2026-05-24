"""Alembic environment.

Runs migrations against the same SQLAlchemy metadata declared in
``app.db.Base``. ``CONET_DATABASE_URL`` overrides the static URL from
``alembic.ini``.
"""

from __future__ import annotations

import asyncio
import os
import re
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context
from app.db import Base  # noqa: F401  (registers tables on Base.metadata)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def _resolve_url() -> str:
    env_url = os.environ.get("CONET_DATABASE_URL")
    if env_url:
        return env_url
    return config.get_main_option("sqlalchemy.url", "")


def _is_async_url(url: str) -> bool:
    return bool(re.match(r"^[a-z0-9]+\+(aiosqlite|asyncpg|aiomysql)", url))


def run_migrations_offline() -> None:
    """Run migrations without a live DB connection (emits SQL)."""
    url = _resolve_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _do_run(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    url = _resolve_url()
    if _is_async_url(url):
        connectable = async_engine_from_config(
            {"sqlalchemy.url": url},
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )

        async def _run() -> None:
            async with connectable.connect() as conn:
                await conn.run_sync(_do_run)
            await connectable.dispose()

        asyncio.run(_run())
    else:
        connectable = engine_from_config(
            {"sqlalchemy.url": url},
            prefix="sqlalchemy.",
            poolclass=pool.NullPool,
        )
        with connectable.connect() as connection:
            _do_run(connection)
        connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
