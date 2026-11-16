from datetime import datetime
from datetime import timedelta
from datetime import timezone
import hashlib
import secrets

from flask import current_app
from flask import request
from flask import Response
from sqlalchemy import delete
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from givvi.errors import ApiError
from givvi.models import LoginSession
from givvi.models import RateBucket
from givvi.models import User

COOKIE_NAME = "givvi_session"
SESSION_DAYS = 7
RATE_WINDOW_SECONDS = 900


def now() -> datetime:
    return current_app.config["CLOCK"]()


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def digest(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def session_record(database: Session, lock: bool = False) -> LoginSession | None:
    cookie = request.cookies.get(COOKIE_NAME, "")
    query = select(LoginSession).where(LoginSession.id == digest(cookie))
    if lock:
        query = query.with_for_update()
    record = database.scalar(query)
    return record if record and utc(record.expires_at) > now() else None


def require_csrf(database: Session) -> LoginSession:
    record = session_record(database)
    token = request.headers.get("X-CSRF-Token", "")
    if (request.headers.get("Origin") != current_app.config["APP_ORIGIN"]
            or not record or not secrets.compare_digest(record.csrf_digest, digest(token))):
        raise ApiError("csrf_invalid", 403)
    return record


def require_user(database: Session) -> User:
    record = session_record(database)
    user = database.scalar(select(User).where(User.id == record.user_id).with_for_update()
                           ) if record and record.user_id else None
    if record and not database.scalar(select(LoginSession).where(LoginSession.id == record.id)):
        user = None
    if not user:
        raise ApiError("unauthenticated", 401)
    return user


def set_cookie(response: Response, identifier: str, authenticated: bool) -> None:
    response.set_cookie(
        COOKIE_NAME,
        identifier,
        max_age=SESSION_DAYS * 86400 if authenticated else 3600,
        secure=current_app.config["COOKIE_SECURE"],
        httponly=True,
        samesite="Lax"
    )


def new_session(database: Session, user_id: str | None = None) -> tuple[str, str]:
    identifier = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(32)
    database.add(LoginSession(
        id=digest(identifier), user_id=user_id, csrf_digest=digest(csrf),
        expires_at=now() + (timedelta(days=SESSION_DAYS) if user_id else timedelta(hours=1)),
    ))
    return identifier, csrf


def throttle(operation: str, email: str = "") -> None:
    limit = current_app.config["AUTH_RATE_LIMIT"]
    window = int(now().timestamp()) // RATE_WINDOW_SECONDS
    identifiers = [f"{operation}:ip:{request.remote_addr}:{window}"]
    if email:
        identifiers.append(f"{operation}:email:{email}:{window}")
    engine = current_app.extensions["database"]
    insert = postgres_insert if engine.dialect.name == "postgresql" else sqlite_insert
    with Session(engine) as database, database.begin():
        database.execute(delete(RateBucket).where(RateBucket.expires_at < now()))
        for identifier in identifiers:
            statement = insert(RateBucket).values(
                id=digest(f'{current_app.config["OUTBOX_KEY"]}:{identifier}'), count=1,
                expires_at=datetime.fromtimestamp((window + 1) * RATE_WINDOW_SECONDS, timezone.utc),
            )
            statement = statement.on_conflict_do_update(
                index_elements=[RateBucket.id], set_={"count": RateBucket.count + 1},
            ).returning(RateBucket.count)
            if database.scalar(statement) > limit:
                raise ApiError("rate_limited", 429)
