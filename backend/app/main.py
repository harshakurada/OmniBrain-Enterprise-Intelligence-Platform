import time
from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from backend.app.api.deps import get_metrics_service
from backend.app.api.v1.router import api_router
from backend.app.config.settings import settings
from backend.app.core.exceptions import register_exception_handlers
from backend.app.core.logging_config import setup_logging
from backend.app.core.startup_validation import StartupValidationError, validate_startup_configuration
from backend.app.database.connection import engine, init_db, readonly_engine
from backend.app.observability.request_context import set_request_id

# Initialize logging before creating the app instance
setup_logging()
logger = logging.getLogger("omnibrain.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Context manager for handling FastAPI application startup and shutdown
    lifecycles. Startup fails fast on critical misconfiguration or database
    initialization failure -- so a container orchestrator sees a crashed
    process (and can restart/alert) rather than a process that started but
    can never actually serve requests.
    """
    logger.info("Application starting up...")

    try:
        validate_startup_configuration()
    except StartupValidationError as exc:
        logger.critical(f"Startup validation failed: {exc}")
        raise

    try:
        init_db()
    except Exception as exc:
        logger.critical(f"Database initialization failed during startup: {exc}")
        raise

    logger.info(
        f"Application startup sequence completed "
        f"(version={settings.APP_VERSION}, environment={settings.ENVIRONMENT})."
    )
    yield

    logger.info("Application shutting down...")
    try:
        engine.dispose()
        readonly_engine.dispose()
        logger.info("Database engine connections disposed.")
    except Exception:
        logger.exception("Error disposing database engines during shutdown.")
    logger.info("Shutdown complete.")


app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Enterprise-grade Agentic Multi-Modal RAG Orchestrator API backend.",
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url=f"{settings.API_V1_PREFIX}/openapi.json",
    lifespan=lifespan,
)

# Register Global CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register Exception Handlers
register_exception_handlers(app)


@app.middleware("http")
async def observability_middleware(request: Request, call_next):
    """Module 6: assigns a per-request correlation id (propagated into every
    log line via `RequestIdLogFilter`, and returned as `X-Request-ID`),
    times the request, and records API latency/status into the process-wide
    `MetricsService`. Never lets an observability failure break the request.
    """
    request_id = set_request_id(request.headers.get("X-Request-ID"))
    started = time.perf_counter()

    response = await call_next(request)

    duration_ms = (time.perf_counter() - started) * 1000
    response.headers["X-Request-ID"] = request_id

    try:
        get_metrics_service().record_api_request(
            request_id=request_id, method=request.method, path=request.url.path,
            status_code=response.status_code, duration_ms=duration_ms,
        )
    except Exception:
        logger.exception("Failed to record API request metrics (non-fatal).")

    logger.info(f"{request.method} {request.url.path} -> {response.status_code} ({duration_ms:.1f} ms)")
    return response


# Register API Router
app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.get("/", include_in_schema=False)
def root():
    """Direct root endpoint to verify application readiness and point to Swagger docs."""
    return {
        "message": f"Welcome to {settings.PROJECT_NAME} Backend API.",
        "documentation": "/docs",
        "status": "online",
        "version": settings.APP_VERSION,
        "environment": settings.ENVIRONMENT,
    }


if __name__ == "__main__":
    import uvicorn

    logger.info(f"Running FastAPI application via Uvicorn on {settings.BACKEND_HOST}:{settings.BACKEND_PORT}")

    uvicorn_kwargs = {
        "host": settings.BACKEND_HOST,
        "port": settings.BACKEND_PORT,
        "reload": settings.DEBUG,
    }
    # Multiple workers are incompatible with --reload, and with this app's
    # in-process singletons (conversation state, metrics, evaluation
    # history) -- each worker would have independent state. Only apply
    # workers when not in debug/reload mode; validate_startup_configuration()
    # already warns if this combination looks unintentional.
    if not settings.DEBUG and settings.UVICORN_WORKERS > 1:
        uvicorn_kwargs["workers"] = settings.UVICORN_WORKERS

    uvicorn.run("backend.app.main:app", **uvicorn_kwargs)
