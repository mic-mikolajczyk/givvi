import hashlib
import json
import logging
from time import perf_counter
import traceback
from uuid import uuid4

from flask import Flask
from flask import g
from flask import jsonify
from flask import request
from flask import Response
from sqlalchemy.exc import SQLAlchemyError
from werkzeug.exceptions import HTTPException


class ApiError(Exception):
    def __init__(self, code: str, status: int, fields: dict[str, str] | None = None) -> None:
        self.code = code
        self.status = status
        self.fields = fields or {}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps({
            "level": record.levelname, "message": record.getMessage(),
            "request_id": getattr(record, "request_id", None),
            "error_type": getattr(record, "error_type", None),
            "stack": getattr(record, "safe_stack", None),
            "route": getattr(record, "route", None),
            "status": getattr(record, "status", None),
            "duration_ms": getattr(record, "duration_ms", None),
            "message_id": getattr(record, "message_id", None),
        })


def configure_errors(app: Flask) -> None:
    for handler in app.logger.handlers:
        handler.setFormatter(JsonFormatter())

    @app.before_request
    def identify_request() -> None:
        g.request_id = str(uuid4())
        g.started_at = perf_counter()

    @app.after_request
    def response_headers(response: Response) -> Response:
        response.headers["X-Request-ID"] = g.request_id
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        if app.config["ENVIRONMENT"] == "production":
            response.headers["Strict-Transport-Security"] = "max-age=31536000"
        if request.method == "GET" and response.status_code == 200 and request.endpoint in {
            "events.list_events", "events.get_event", "events.get_event_drawing_status", "events.get_participant_wishlist",
        }:
            response.set_etag(hashlib.sha256(response.get_data()).hexdigest())
            response.make_conditional(request)
        app.logger.info("Request completed", extra={
            "request_id": g.request_id,
            "route": request.url_rule.rule if request.url_rule else "unmatched",
            "status": response.status_code,
            "duration_ms": round((perf_counter() - g.started_at) * 1000, 2),
        })
        return response

    @app.errorhandler(ApiError)
    def domain_error(error: ApiError) -> tuple[Response, int]:
        response = jsonify(code=error.code, message=error.code, field_errors=error.fields, request_id=g.request_id)
        if error.status == 429:
            response.headers["Retry-After"] = "900"
        return response, error.status

    @app.errorhandler(HTTPException)
    def http_error(error: HTTPException) -> tuple[Response, int]:
        return domain_error(ApiError("invalid_request", error.code or 400))

    @app.errorhandler(Exception)
    def unexpected_error(error: Exception) -> tuple[Response, int]:
        app.logger.error("Request failed", extra={
            "request_id": g.request_id, "error_type": type(error).__name__,
            "safe_stack": [
                {"file": frame.filename.rsplit("/", 1)[-1], "line": frame.lineno, "function": frame.name}
                for frame in traceback.extract_tb(error.__traceback__)
            ],
        })
        code = "service_unavailable" if isinstance(error, SQLAlchemyError) else "internal_error"
        return domain_error(ApiError(code, 503 if code == "service_unavailable" else 500))
