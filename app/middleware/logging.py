"""
Structured (JSON) logging with a per-request correlation ID.

Every log line emitted during a request carries the same `request_id` —
either propagated from an inbound `X-Request-ID` header (useful when
Nginx or an upstream gateway already assigns one) or generated fresh —
so a single request's story can be grepped out of aggregated logs in
Loki/Grafana with one filter.
"""

import logging
import time
import uuid
from contextvars import ContextVar

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")

REQUEST_ID_HEADER = "X-Request-ID"


def _add_request_id(logger, method_name, event_dict):
    event_dict["request_id"] = request_id_ctx.get()
    return event_dict


def configure_logging(log_level: str = "INFO") -> None:
    logging.basicConfig(level=log_level, format="%(message)s")

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            _add_request_id,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(log_level)),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


class RequestContextMiddleware(BaseHTTPMiddleware):
    """Assigns/propagates a request ID and logs one structured line per request."""

    def __init__(self, app):
        super().__init__(app)
        self.logger = structlog.get_logger("api.request")

    async def dispatch(self, request: Request, call_next):
        incoming_id = request.headers.get(REQUEST_ID_HEADER)
        req_id = incoming_id or str(uuid.uuid4())
        token = request_id_ctx.set(req_id)

        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            self.logger.exception(
                "request_failed", method=request.method, path=request.url.path,
            )
            raise
        finally:
            request_id_ctx.reset(token)

        duration_ms = round((time.perf_counter() - start) * 1000, 2)
        response.headers[REQUEST_ID_HEADER] = req_id
        self.logger.info(
            "request_completed",
            method=request.method,
            path=request.url.path,
            status_code=response.status_code,
            duration_ms=duration_ms,
        )
        return response
