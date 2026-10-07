import json
import logging
import traceback
from uuid import uuid4

from flask import Flask
from flask import g
from flask import jsonify
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
        })


def configure_errors(app: Flask) -> None:
    for handler in app.logger.handlers:
        handler.setFormatter(JsonFormatter())

    @app.before_request
    def identify_request() -> None:
        g.request_id = str(uuid4())

    @app.after_request
    def response_headers(response: Response) -> Response:
        response.headers["X-Request-ID"] = g.request_id
        response.headers["Cache-Control"] = "no-store"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
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
