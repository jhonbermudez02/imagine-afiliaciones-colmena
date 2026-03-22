import logging
import time
import uuid
from contextvars import ContextVar

from fastapi import Request

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


def setup_logging() -> None:
    base_factory = logging.getLogRecordFactory()

    def record_factory(*args, **kwargs):  # type: ignore[no-untyped-def]
        record = base_factory(*args, **kwargs)
        if not hasattr(record, "request_id"):
            record.request_id = request_id_ctx.get("-")
        return record

    logging.setLogRecordFactory(record_factory)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s request_id=%(request_id)s %(message)s",
    )
    root = logging.getLogger()
    has_filter = any(isinstance(f, RequestIdFilter) for f in root.filters)
    if not has_filter:
        root.addFilter(RequestIdFilter())
    for handler in root.handlers:
        handler_has_filter = any(isinstance(f, RequestIdFilter) for f in handler.filters)
        if not handler_has_filter:
            handler.addFilter(RequestIdFilter())


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_ctx.get("-")
        return True


def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    has_filter = any(isinstance(f, RequestIdFilter) for f in logger.filters)
    if not has_filter:
        logger.addFilter(RequestIdFilter())
    return logger


def get_or_create_request_id(request: Request) -> str:
    incoming = request.headers.get("X-Request-ID")
    if incoming and incoming.strip():
        return incoming.strip()
    return uuid.uuid4().hex


def request_log_payload(request: Request, status_code: int, started_at: float) -> str:
    elapsed_ms = int((time.time() - started_at) * 1000)
    return (
        f'method="{request.method}" '
        f'path="{request.url.path}" '
        f"status={status_code} "
        f"duration_ms={elapsed_ms}"
    )
