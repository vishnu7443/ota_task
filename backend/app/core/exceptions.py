import logging
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

logger = logging.getLogger(__name__)


class AppError(Exception):
    """Base domain/application error translated cleanly into structured HTTP responses."""

    def __init__(
        self,
        message: str,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        error_code: str = "DOMAIN_ERROR",
        details: Any = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.error_code = error_code
        self.details = details


class AuthenticationError(AppError):
    def __init__(self, message: str = "Invalid authentication credentials.") -> None:
        super().__init__(message, status.HTTP_401_UNAUTHORIZED, "AUTHENTICATION_FAILED")


class AuthorizationError(AppError):
    def __init__(self, message: str = "You do not have permission for this action.") -> None:
        super().__init__(message, status.HTTP_403_FORBIDDEN, "FORBIDDEN")


class NotFoundError(AppError):
    def __init__(self, message: str = "Requested resource was not found.") -> None:
        super().__init__(message, status.HTTP_404_NOT_FOUND, "NOT_FOUND")


class ConflictError(AppError):
    def __init__(
        self, message: str, details: Any = None, error_code: str = "CONFLICT"
    ) -> None:
        super().__init__(message, status.HTTP_409_CONFLICT, error_code, details=details)


class DomainValidationError(AppError):
    def __init__(self, message: str, details: Any = None) -> None:
        super().__init__(
            message, status.HTTP_422_UNPROCESSABLE_CONTENT, "DOMAIN_VALIDATION_ERROR", details=details
        )


def _error_response(status_code: int, code: str, message: str, details: Any = None) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "details": details}},
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def handle_app_error(_request: Request, exc: AppError) -> JSONResponse:
        return _error_response(exc.status_code, exc.error_code, exc.message, exc.details)

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
        return _error_response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "REQUEST_VALIDATION_ERROR",
            "Request validation failed.",
            exc.errors(),
        )

    @app.exception_handler(IntegrityError)
    async def handle_integrity_error(_request: Request, exc: IntegrityError) -> JSONResponse:
        logger.warning("Database integrity violation: %s", exc)
        return _error_response(
            status.HTTP_409_CONFLICT,
            "DATABASE_INTEGRITY_ERROR",
            "Operation violates database integrity constraints.",
        )

    @app.exception_handler(SQLAlchemyError)
    async def handle_db_error(_request: Request, exc: SQLAlchemyError) -> JSONResponse:
        logger.exception("Database operation failed: %s", exc)
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "DATABASE_ERROR",
            "A database error occurred while processing the request.",
        )

    @app.exception_handler(Exception)
    async def handle_unexpected_error(_request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception: %s", exc)
        return _error_response(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "INTERNAL_SERVER_ERROR",
            "An unexpected internal error occurred.",
        )
