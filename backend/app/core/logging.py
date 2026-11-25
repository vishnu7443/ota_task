import contextvars
import json
import logging
import sys
from datetime import UTC, datetime

_correlation_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "ota_correlation_id", default=None
)


def set_request_correlation_id(req_id: str | None) -> contextvars.Token[str | None]:
    return _correlation_id_ctx.set(req_id)


def reset_request_correlation_id(token: contextvars.Token[str | None]) -> None:
    _correlation_id_ctx.reset(token)


def get_request_correlation_id() -> str | None:
    return _correlation_id_ctx.get()


class StructuredJsonFormatter(logging.Formatter):
    """Formats logs as structured JSON lines for deterministic auditability."""

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        req_id = getattr(record, "request_id", None) or get_request_correlation_id()
        if req_id:
            payload["request_id"] = req_id
        for key in ("method", "path", "status_code", "user_id", "role"):
            if hasattr(record, key):
                payload[key] = getattr(record, key)
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    root = logging.getLogger()
    root.setLevel(level.upper())
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredJsonFormatter())
    root.handlers = [handler]
