import logging
from typing import Any, Dict
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from backend.app.config.settings import settings
from backend.app.observability.request_context import get_request_id

logger = logging.getLogger("omnibrain.exceptions")


class AppException(Exception):
    """Base application exception for OmniBrain."""

    def __init__(
        self,
        message: str,
        status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR,
        details: Any = None,
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.details = details


class DatabaseException(AppException):
    """Exception raised for database errors."""

    def __init__(self, message: str, details: Any = None):
        super().__init__(
            message=message,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            details=details,
        )


class ValidationException(AppException):
    """Exception raised for business validation failures."""

    def __init__(self, message: str, details: Any = None):
        super().__init__(
            message=message,
            status_code=status.HTTP_400_BAD_REQUEST,
            details=details,
        )


class NotFoundException(AppException):
    """Exception raised when a resource is not found."""

    def __init__(self, message: str, details: Any = None):
        super().__init__(
            message=message,
            status_code=status.HTTP_404_NOT_FOUND,
            details=details,
        )


class ExternalAPIException(AppException):
    """Exception raised for failures when communicating with external APIs (e.g. OpenAI, Langfuse)."""

    def __init__(self, message: str, details: Any = None):
        super().__init__(
            message=message,
            status_code=status.HTTP_502_BAD_GATEWAY,
            details=details,
        )


def register_exception_handlers(app: FastAPI) -> None:
    """Registers global exception handlers for the FastAPI application."""

    @app.exception_handler(AppException)
    async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
        logger.error(f"AppException: {exc.message} | Details: {exc.details}")
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "request_id": get_request_id(),
                "error": {
                    "type": exc.__class__.__name__,
                    "message": exc.message,
                    "details": exc.details,
                },
            },
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        logger.error(f"HTTPException: {exc.detail} | Status: {exc.status_code}")
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "request_id": get_request_id(),
                "error": {
                    "type": "HTTPException",
                    "message": exc.detail,
                    "details": None,
                },
            },
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        details = exc.errors()
        message = "Validation error on requested payload"
        logger.error(f"ValidationError: {message} | Details: {details}")
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "success": False,
                "request_id": get_request_id(),
                "error": {
                    "type": "RequestValidationError",
                    "message": message,
                    "details": details,
                },
            },
        )

    @app.exception_handler(Exception)
    async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception(f"Unhandled Exception: {str(exc)}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "success": False,
                "request_id": get_request_id(),
                "error": {
                    "type": "InternalServerError",
                    "message": "An unexpected error occurred. Please check the logs.",
                    "details": str(exc) if settings.DEBUG else None,
                },
            },
        )
