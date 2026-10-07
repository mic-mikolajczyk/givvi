from collections.abc import Callable
from functools import wraps
import secrets

from flask import Blueprint
from flask import current_app
from flask import jsonify
from flask import request
from flask import Response
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from givvi.accounts import services
from givvi.accounts.security import COOKIE_NAME
from givvi.accounts.security import digest
from givvi.accounts.security import new_session
from givvi.accounts.security import require_csrf
from givvi.accounts.security import require_user
from givvi.accounts.security import session_record
from givvi.accounts.security import set_cookie
from givvi.accounts.security import throttle
from givvi.accounts.services import normalized_email
from givvi.errors import ApiError
from givvi.models import User

accounts = Blueprint("accounts", __name__, url_prefix="/api/auth")


def request_body() -> dict:
    body = request.get_json()
    if not isinstance(body, dict):
        raise ApiError("invalid_request", 400)
    return body


@accounts.get("/csrf")
def csrf() -> Response:
    throttle("csrf")
    with Session(current_app.extensions["database"]) as database, database.begin():
        record = session_record(database, lock=True)
        identifier = None
        if record:
            token = secrets.token_urlsafe(32)
            record.csrf_digest = digest(token)
        else:
            identifier, token = new_session(database)
        response = jsonify(csrf_token=token)
        if identifier:
            set_cookie(response, identifier, False)
    return response


@accounts.post("/register")
def registration() -> tuple[Response, int]:
    engine = current_app.extensions["database"]
    try:
        with Session(engine) as database, database.begin():
            require_csrf(database)
            body = request_body()
            email = normalized_email(body.get("email"))
            throttle("register", email)
            user = services.register(database, body)
            response = signed_in_response(database, user)
    except IntegrityError:
        with Session(engine) as database:
            if not database.scalar(select(User).where(User.email == email)):
                raise
        raise ApiError("registration_failed", 409)
    return response, 201


def mutation(function: Callable) -> Callable:
    @wraps(function)
    def wrapped():
        with Session(current_app.extensions["database"]) as database, database.begin():
            require_csrf(database)
            body = request_body()
            email = body.get("email", "")
            throttle(function.__name__, normalized_email(email) if email else "")
            return function(database, body)
    return wrapped


def user_view(user: User) -> dict:
    return {
        "id": user.id, "name": user.name, "email": user.email,
        "language": user.language, "pending_email": user.pending_email,
    }


def signed_in_response(database: Session, user: User) -> Response:
    record = session_record(database)
    if record:
        database.delete(record)
    identifier, token = new_session(database, user.id)
    response = jsonify(user=user_view(user), csrf_token=token)
    set_cookie(response, identifier, True)
    return response


@accounts.post("/verify")
@mutation
def verify(database: Session, body: dict) -> Response:
    services.verify_token(database, body.get("token"))
    return jsonify(code="email_verified")


@accounts.post("/login")
@mutation
def login(database: Session, body: dict) -> Response:
    user = services.authenticate(database, body)
    return signed_in_response(database, user)


@accounts.get("/me")
def me() -> Response:
    with Session(current_app.extensions["database"]) as database, database.begin():
        return jsonify(user=user_view(require_user(database)))


@accounts.post("/logout")
@mutation
def logout(database: Session, body: dict) -> Response:
    record = session_record(database)
    if record:
        database.delete(record)
    response = jsonify(code="logged_out")
    response.delete_cookie(COOKIE_NAME, secure=current_app.config["COOKIE_SECURE"], httponly=True, samesite="Lax")
    return response


@accounts.post("/forgot-password")
@mutation
def forgot_password(database: Session, body: dict) -> tuple[Response, int]:
    services.request_password_reset(database, body)
    return jsonify(code="check_email"), 202


@accounts.post("/reset-password")
@mutation
def password_reset(database: Session, body: dict) -> Response:
    services.reset_password(database, body)
    return jsonify(code="password_updated")


@accounts.post("/profile")
@mutation
def profile(database: Session, body: dict) -> Response:
    user = require_user(database)
    services.update_profile(user, body)
    return jsonify(user=user_view(user), code="profile_updated")


@accounts.post("/change-password")
@mutation
def password_change(database: Session, body: dict) -> Response:
    services.change_password(database, require_user(database), body)
    return jsonify(code="password_updated")


@accounts.post("/change-email")
@mutation
def email_change(database: Session, body: dict) -> tuple[Response, int]:
    services.change_email(database, require_user(database), body)
    return jsonify(code="check_email"), 202
