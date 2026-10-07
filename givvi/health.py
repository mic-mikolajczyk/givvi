from flask import Blueprint
from flask import current_app
from flask import jsonify
from flask import Response
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

health = Blueprint("health", __name__, url_prefix="/api/health")


@health.get("/live")
def liveness() -> Response:
    """Report process availability without requiring external dependencies."""
    response = jsonify(status="alive")
    response.headers["Cache-Control"] = "no-store"
    return response


@health.get("/ready")
def readiness() -> tuple[Response, int]:
    """Report whether the application can reach its database."""
    status_code = 200
    status = "ready"
    try:
        with current_app.extensions["database"].connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError:
        current_app.logger.warning("Database readiness check failed")
        status_code = 503
        status = "unavailable"

    response = jsonify(status=status)
    response.headers["Cache-Control"] = "no-store"
    return response, status_code
