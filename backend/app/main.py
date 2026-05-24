"""FastAPI application factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import __version__
from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.core.middleware import (
    AccessLogMiddleware,
    RateLimitMiddleware,
    RequestContextMiddleware,
)
from app.core.webhooks import dispatcher
from app.db import dispose_engine, init_db
from app.routers import (
    admin,
    calibrate,
    edges,
    events,
    frames,
    inspect,
    lines,
    meshes,
    meta,
    pricing,
    webhooks,
)

logger = get_logger("conet.startup")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    await init_db()
    dispatcher.start()
    logger.info(
        "service_started",
        extra={
            "version": __version__,
            "environment": settings.environment,
            "auth_required": settings.auth_required,
        },
    )
    try:
        yield
    finally:
        await dispatcher.stop()
        await dispose_engine()
        logger.info("service_stopped")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Conet Tactile Cloud",
        version=__version__,
        summary="Ingestion, calibration, and inspection service for the Tactile Mesh fleet.",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=False,
    )
    app.add_middleware(AccessLogMiddleware)
    app.add_middleware(RateLimitMiddleware)
    app.add_middleware(RequestContextMiddleware)

    @app.exception_handler(RequestValidationError)
    async def _on_validation_error(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": exc.errors(), "type": "validation_error"},
        )

    @app.exception_handler(Exception)
    async def _on_unhandled(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            "unhandled_exception",
            extra={"path": request.url.path, "method": request.method},
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "internal server error", "type": exc.__class__.__name__},
        )

    app.include_router(meta.router)
    app.include_router(lines.router)
    app.include_router(frames.router)
    app.include_router(calibrate.router)
    app.include_router(inspect.router)
    app.include_router(events.router)
    app.include_router(edges.router)
    app.include_router(meshes.router)
    app.include_router(pricing.router)
    app.include_router(webhooks.router)
    app.include_router(admin.router)
    return app


app = create_app()
