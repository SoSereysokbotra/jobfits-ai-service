"""FastAPI application entry point.

`uvicorn app.main:app --reload` serves this. Routers are mounted under /api/v1.
Part 1 wires health + embed; resume and generate routers are added in later parts.
"""

from __future__ import annotations

import logging
import time

from fastapi import FastAPI, Request

from app.core.errors import register_exception_handlers
from app.routers import embed, generate, health, resume

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ai-service")


def create_app() -> FastAPI:
    app = FastAPI(title="jobfits-ai-service", version="1.0.0")

    register_exception_handlers(app)

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "%s %s -> %d (%.0fms)",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response

    app.include_router(health.router, prefix="/api/v1", tags=["health"])
    app.include_router(embed.router, prefix="/api/v1", tags=["embed"])
    app.include_router(resume.router, prefix="/api/v1", tags=["resume"])
    app.include_router(generate.router, prefix="/api/v1", tags=["generate"])

    return app


app = create_app()
