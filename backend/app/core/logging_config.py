import json
import logging
import os
import re
from logging.handlers import RotatingFileHandler
from backend.app.config.settings import settings
from backend.app.observability.request_context import get_request_id


class RequestIdLogFilter(logging.Filter):
    """Injects the current request's id (Module 6) into every log record,
    so log lines can be correlated back to a specific API request even
    across the multiple agent/service log calls a single request triggers.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True


class JsonLogFormatter(logging.Formatter):
    """Renders log records as single-line JSON (Module 7), for deployments
    where a log aggregator (e.g. CloudWatch, Loki, ELK) parses structured
    fields rather than free-text lines. Selected via `LOG_FORMAT=json`.
    """

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "request_id": getattr(record, "request_id", "-"),
            "logger": record.name,
            "function": record.funcName,
            "line": record.lineno,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload)


def parse_rotation_size(rotation_str: str) -> int:
    """Parses a size string like '10 MB', '500 KB' or '1 GB' into bytes.

    Defaults to 10MB if parsing fails.
    """
    match = re.match(r"^(\d+)\s*(B|KB|MB|GB)$", rotation_str.strip(), re.IGNORECASE)
    if not match:
        return 10 * 1024 * 1024  # 10 MB default

    value, unit = match.groups()
    num = int(value)
    unit = unit.upper()

    units = {"B": 1, "KB": 1024, "MB": 1024 * 1024, "GB": 1024 * 1024 * 1024}

    return num * units.get(unit, 1024 * 1024 * 10)


def setup_logging() -> None:
    """Configures centralized logging for the FastAPI application.

    Supports console logging and rotating file logging.
    """
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)

    # Core logger configuration
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Avoid duplicate handlers if setup is called multiple times
    if root_logger.handlers:
        root_logger.handlers.clear()

    # Formatter (Module 6: includes the per-request correlation id; Module 7:
    # optional JSON output for log aggregators via LOG_FORMAT=json).
    if settings.LOG_FORMAT == "json":
        formatter: logging.Formatter = JsonLogFormatter()
    else:
        formatter = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | req=%(request_id)s | %(name)s:%(funcName)s:%(lineno)d - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    request_id_filter = RequestIdLogFilter()

    # Console Handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(request_id_filter)
    root_logger.addHandler(console_handler)

    # File Handler
    log_file_path = settings.LOG_FILE_PATH
    if log_file_path:
        # Create directories if they do not exist
        log_dir = os.path.dirname(os.path.abspath(log_file_path))
        os.makedirs(log_dir, exist_ok=True)

        max_bytes = parse_rotation_size(settings.LOG_ROTATION)
        file_handler = RotatingFileHandler(
            filename=log_file_path,
            maxBytes=max_bytes,
            backupCount=settings.LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        file_handler.addFilter(request_id_filter)
        root_logger.addHandler(file_handler)

    # Set external libraries to warning to avoid cluttering the console
    logging.getLogger("uvicorn.error").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)

    logging.info("Logging successfully initialized.")
