"""Async SQLAlchemy setup."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import datetime

from sqlalchemy import DateTime, Float, Integer, String, func
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.config import settings


class Base(DeclarativeBase):
    """SQLAlchemy declarative base."""


class Line(Base):
    """A registered conveyor line."""

    __tablename__ = "lines"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    customer_tag: Mapped[str] = mapped_column(String(128), default="")
    rows: Mapped[int] = mapped_column(Integer)
    cols: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32), default="awaiting_calibration")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    calibrated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    n_samples: Mapped[int] = mapped_column(Integer, default=0)
    drift: Mapped[float] = mapped_column(Float, default=0.0)


class Inspection(Base):
    """A single inspection event."""

    __tablename__ = "inspections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    line_id: Mapped[str] = mapped_column(String(64), index=True)
    score: Mapped[float] = mapped_column(Float)
    hits: Mapped[int] = mapped_column(Integer)
    verdict: Mapped[str] = mapped_column(String(16))  # "pass" | "fail"
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )


_engine = create_async_engine(settings.database_url, echo=False, future=True)
_session_factory = async_sessionmaker(_engine, expire_on_commit=False)


async def init_db() -> None:
    """Create tables if they don't exist."""
    async with _engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding an async session."""
    async with _session_factory() as session:
        yield session


async def dispose_engine() -> None:
    await _engine.dispose()
