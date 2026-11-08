import secrets

from flask import Blueprint
from flask import current_app
from flask import jsonify
from flask import request
from flask import Response
from sqlalchemy import func
from sqlalchemy import select
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from givvi.accounts.security import now
from givvi.accounts.security import utc
from givvi.models import EmailMessage

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


@health.get("/metrics")
def metrics() -> Response:
    token = current_app.config.get("METRICS_TOKEN", "")
    if not token or not secrets.compare_digest(request.headers.get("Authorization", ""), f"Bearer {token}"):
        return Response(status=404)
    with Session(current_app.extensions["database"]) as database:
        pending, failed, oldest = database.execute(select(
            func.count().filter(EmailMessage.payload.is_not(None), EmailMessage.failed_at.is_(None)),
            func.count().filter(EmailMessage.failed_at.is_not(None)),
            func.min(EmailMessage.available_at).filter(EmailMessage.payload.is_not(None)),
        )).one()
    age = max(0, int((now() - utc(oldest)).total_seconds())) if oldest else 0
    return Response(
        f"givvi_outbox_pending {pending}\ngivvi_outbox_failed {failed}\ngivvi_outbox_oldest_seconds {age}\n",
        content_type="text/plain; version=0.0.4; charset=utf-8",
    )
