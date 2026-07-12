"""
FastAPI application entry point.

WILL CONTAIN (Phase 0):
- A `create_app()` factory that instantiates FastAPI, registers the routers from
  `app.routers.*` under the `/api/v1` prefix, installs the exception handlers from
  `app.core.errors`, and adds request-logging middleware.
- Module-level `app = create_app()` so `uvicorn app.main:app` works.

NO LOGIC YET — placeholder. Implement per BUILD_PLAN.md §6 Phase 0.
"""
