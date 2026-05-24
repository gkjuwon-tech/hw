"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.db import dispose_engine, init_db
from app.routers import calibrate, events, frames, inspect, lines


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    await init_db()
    try:
        yield
    finally:
        await dispose_engine()


app = FastAPI(
    title="Conet Tactile Cloud",
    version=__version__,
    summary="Ingestion, calibration, and inspection service for the Tactile Mesh fleet.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=False,
)


@app.get("/healthz", tags=["meta"])
async def healthz() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


app.include_router(lines.router)
app.include_router(frames.router)
app.include_router(calibrate.router)
app.include_router(inspect.router)
app.include_router(events.router)
