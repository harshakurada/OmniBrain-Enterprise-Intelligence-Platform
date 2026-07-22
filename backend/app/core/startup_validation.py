import logging
import os
from typing import List
from backend.app.config.settings import settings

logger = logging.getLogger("omnibrain.startup")


class StartupValidationError(Exception):
    """Raised when a critical, unrecoverable misconfiguration is detected
    at startup. The application should fail fast rather than start into a
    broken state.
    """


def validate_startup_configuration() -> None:
    """Validates the running configuration before the application accepts
    traffic.

    Critical problems (a required directory that cannot be created, an
    empty `DATABASE_URL`) raise `StartupValidationError`, aborting startup
    -- this matches container-orchestrator expectations (crash loudly so
    the platform can restart/alert) rather than running silently broken.

    Soft problems (development defaults left in place in production) are
    logged as warnings only, consistent with the application's existing
    philosophy of degrading gracefully around optional external
    dependencies (OpenAI, Qdrant) rather than refusing to start.
    """
    _validate_required_directories()
    _validate_database_url()
    _warn_on_insecure_production_settings()
    logger.info(
        f"Startup configuration validated (version={settings.APP_VERSION}, "
        f"environment={settings.ENVIRONMENT})."
    )


def _validate_required_directories() -> None:
    log_dir = os.path.dirname(settings.LOG_FILE_PATH) or "."
    for path in (settings.UPLOAD_DIR, settings.ASSETS_DIR, settings.FAISS_STORAGE_PATH, log_dir):
        try:
            os.makedirs(path, exist_ok=True)
        except OSError as exc:
            raise StartupValidationError(f"Cannot create required directory '{path}': {exc}") from exc


def _validate_database_url() -> None:
    if not settings.DATABASE_URL or not settings.DATABASE_URL.strip():
        raise StartupValidationError("DATABASE_URL must not be empty.")

    if settings.DATABASE_URL.startswith("sqlite"):
        # e.g. "sqlite:///./storage/omnibrain.db" -> "./storage/omnibrain.db"
        db_path = settings.DATABASE_URL.split("///", 1)[-1]
        db_dir = os.path.dirname(db_path)
        if db_dir:
            try:
                os.makedirs(db_dir, exist_ok=True)
            except OSError as exc:
                raise StartupValidationError(
                    f"Cannot create SQLite database directory '{db_dir}': {exc}"
                ) from exc


def _warn_on_insecure_production_settings() -> None:
    if not settings.is_production:
        return

    warnings: List[str] = []
    if settings.DEBUG:
        warnings.append("DEBUG=True in production exposes internal error details to API clients.")
    if settings.CORS_ORIGINS in (["*"], "*"):
        warnings.append("CORS_ORIGINS is wildcarded ('*') in production; restrict it to known frontend origins.")
    if not settings.OPENAI_API_KEY or settings.OPENAI_API_KEY == "mock-key" or settings.OPENAI_API_KEY.startswith("your-"):
        warnings.append(
            "OPENAI_API_KEY looks like a placeholder; LLM-backed features will degrade "
            "gracefully (per-agent fallbacks) but will not actually function."
        )
    if settings.UVICORN_WORKERS > 1:
        warnings.append(
            "UVICORN_WORKERS > 1: conversation state, metrics, and evaluation history are "
            "in-process singletons, so each worker process has independent state."
        )

    for warning in warnings:
        logger.warning(f"[startup-validation] {warning}")
