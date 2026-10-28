from datetime import timedelta
import json
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError
from argon2.exceptions import VerificationError
from cryptography.fernet import Fernet
from email_validator import EmailNotValidError
from email_validator import validate_email
from flask import current_app
from sqlalchemy import delete
from sqlalchemy import or_
from sqlalchemy import select
from sqlalchemy import update
from sqlalchemy.orm import Session

from givvi.accounts.security import digest
from givvi.accounts.security import now
from givvi.accounts.security import utc
from givvi.errors import ApiError
from givvi.models import AccountDeletionRecord
from givvi.models import AccountToken
from givvi.models import EmailMessage
from givvi.models import Event
from givvi.models import EventParticipant
from givvi.models import Gift
from givvi.models import LoginSession
from givvi.models import User
from givvi.models import Wishlist

MINIMUM_PASSWORD_LENGTH = 12
MAXIMUM_PASSWORD_LENGTH = 128
DELETED_USER_LABEL = "Deleted user"


def normalized_email(value: object) -> str:
    try:
        if not isinstance(value, str) or len(value) > 254:
            raise ApiError("validation_error", 422, {"email": "invalid_email"})
        return validate_email(value.strip(), check_deliverability=False).normalized.casefold()
    except EmailNotValidError as error:
        raise ApiError("validation_error", 422, {"email": "invalid_email"}) from error


def validate_password(password: object) -> str:
    if not isinstance(password, str) or not MINIMUM_PASSWORD_LENGTH <= len(password) <= MAXIMUM_PASSWORD_LENGTH:
        raise ApiError("validation_error", 422, {"password": "password_length"})
    return password


def validate_name(name: object) -> str:
    if not isinstance(name, str) or not 1 <= len(name.strip()) <= 120:
        raise ApiError("validation_error", 422, {"name": "name_length"})
    return name.strip()


def token_email(
    database: Session,
    user: User,
    purpose: str,
    target_email: str | None = None
) -> None:
    token = secrets.token_urlsafe(32)
    expires = now() + (timedelta(minutes=30) if purpose == "reset" else timedelta(hours=24))
    database.execute(delete(AccountToken).where(AccountToken.user_id == user.id, AccountToken.purpose == purpose))
    database.add(AccountToken(id=digest(token), user_id=user.id,
                 purpose=purpose, target_email=target_email, expires_at=expires))
    translations = {
        "en": {"reset": "Reset your password", "email": "Confirm your new email"},
        "pl": {"reset": "Zresetuj hasło", "email": "Potwierdź nowy adres email"},
    }
    title = translations.get(user.language, translations["en"])[purpose]
    path = "reset-password" if purpose == "reset" else "verify"
    link = f'{current_app.config["APP_ORIGIN"]}/{path}#token={token}'
    payload = json.dumps({"to": target_email or user.email, "subject": title,
                         "body": f"{title}\n\n{link}"}, ensure_ascii=False)
    encrypted = Fernet(current_app.config["OUTBOX_KEY"].encode()).encrypt(payload.encode()).decode()
    database.add(EmailMessage(user_id=user.id, payload=encrypted, available_at=now(), expires_at=expires))


def register(database: Session, body: dict) -> User:
    email = normalized_email(body.get("email"))
    name = validate_name(body.get("name"))
    password = validate_password(body.get("password"))
    language = body.get("language", "en")
    if language not in ("en", "pl"):
        raise ApiError("validation_error", 422, {"language": "invalid_language"})
    password_hash = PasswordHasher().hash(password)
    if database.scalar(select(User).where(User.email == email)):
        raise ApiError("registration_failed", 409)
    user = User(email=email, name=name, password_hash=password_hash, language=language)
    database.add(user)
    database.flush()
    database.add(Wishlist(user_id=user.id))
    return user


def password_matches(user: User | None, password: object) -> bool:
    if not isinstance(password, str) or len(password) > MAXIMUM_PASSWORD_LENGTH:
        return False
    password_hash = user.password_hash if user else current_app.extensions["dummy_password_hash"]
    try:
        matches = PasswordHasher().verify(password_hash, password)
        return bool(user and matches)
    except (VerificationError, InvalidHashError):
        return False


def authenticate(database: Session, body: dict) -> User:
    email = normalized_email(body.get("email"))
    user = database.scalar(select(User).where(User.email == email).with_for_update())
    if not password_matches(user, body.get("password")):
        raise ApiError("invalid_credentials", 401)
    if PasswordHasher().check_needs_rehash(user.password_hash):
        user.password_hash = PasswordHasher().hash(body["password"])
    return user


def token_owner(database: Session, raw_token: object) -> tuple[User, AccountToken]:
    if not isinstance(raw_token, str) or not 1 <= len(raw_token) <= 128:
        raise ApiError("token_invalid", 400)
    token_id = digest(raw_token)
    initial = database.get(AccountToken, token_id)
    if not initial:
        raise ApiError("token_invalid", 400)
    user = database.scalar(select(User).where(User.id == initial.user_id).with_for_update())
    token = database.scalar(select(AccountToken).where(AccountToken.id == token_id).with_for_update())
    if not user or not token or utc(token.expires_at) <= now():
        raise ApiError("token_invalid", 400)
    return user, token


def verify_token(database: Session, raw_token: object) -> None:
    user, token = token_owner(database, raw_token)
    if token.purpose != "email" or token.target_email != user.pending_email:
        raise ApiError("token_invalid", 400)
    if database.scalar(select(User).where(User.email == token.target_email, User.id != user.id)):
        raise ApiError("email_unavailable", 409)
    user.email = token.target_email
    user.pending_email = None
    revoke_credentials(database, user.id)


def revoke_credentials(database: Session, user_id: str) -> None:
    database.execute(delete(LoginSession).where(LoginSession.user_id == user_id))
    database.execute(delete(AccountToken).where(AccountToken.user_id == user_id))
    database.execute(update(User).where(User.id == user_id).values(pending_email=None))


def request_password_reset(database: Session, body: dict) -> None:
    email = normalized_email(body.get("email"))
    user = database.scalar(select(User).where(User.email == email).with_for_update())
    if user:
        token_email(database, user, "reset")


def reset_password(database: Session, body: dict) -> None:
    password = validate_password(body.get("password"))
    user, token = token_owner(database, body.get("token"))
    if token.purpose != "reset":
        raise ApiError("token_invalid", 400)
    user.password_hash = PasswordHasher().hash(password)
    revoke_credentials(database, user.id)


def update_profile(user: User, body: dict) -> None:
    user.name = validate_name(body.get("name"))
    if body.get("language") not in ("en", "pl"):
        raise ApiError("validation_error", 422, {"language": "invalid_language"})
    user.language = body["language"]


def change_password(database: Session, user: User, body: dict) -> None:
    if not password_matches(user, body.get("current_password")):
        raise ApiError("invalid_credentials", 401)
    user.password_hash = PasswordHasher().hash(validate_password(body.get("password")))
    revoke_credentials(database, user.id)


def change_email(database: Session, user: User, body: dict) -> None:
    if not password_matches(user, body.get("current_password")):
        raise ApiError("invalid_credentials", 401)
    email = normalized_email(body.get("email"))
    if email == user.email or database.scalar(select(User).where((User.email == email) | (User.pending_email == email))):
        raise ApiError("email_unavailable", 409)
    user.pending_email = email
    token_email(database, user, "email", email)


def delete_account(database: Session, user: User, body: dict) -> None:
    if not password_matches(user, body.get("current_password")):
        raise ApiError("invalid_credentials", 401)
    active_admin_event = database.scalar(select(Event.id).where(
        Event.admin_id == user.id,
        Event.cancelled.is_(False),
    ).limit(1).with_for_update())
    if active_admin_event:
        raise ApiError("admin_events_require_handover", 409)

    database.add(AccountDeletionRecord(user_id=user.id, deleted_at=now()))
    _erase_account_data(database, user.id)


def _erase_account_data(database: Session, user_id: str) -> None:
    owned_event_ids = select(Event.id).where(Event.admin_id == user_id)
    database.execute(delete(EmailMessage).where(or_(
        EmailMessage.user_id == user_id,
        EmailMessage.event_id.in_(owned_event_ids),
    )))
    database.execute(update(EventParticipant).where(EventParticipant.user_id == user_id).values(
        name=DELETED_USER_LABEL,
        user_id=None,
    ))
    database.execute(update(Event).where(Event.admin_id == user_id).values(
        admin_id=None,
        cancelled=True,
        invite_token_hash=None,
        invite_token_encrypted=None,
    ))
    database.execute(delete(Gift).where(Gift.wishlist_id == user_id))
    database.execute(delete(Wishlist).where(Wishlist.user_id == user_id))
    database.execute(delete(LoginSession).where(LoginSession.user_id == user_id))
    database.execute(delete(AccountToken).where(AccountToken.user_id == user_id))
    database.execute(delete(User).where(User.id == user_id))


def reapply_account_deletions(database: Session) -> int:
    records = list(database.scalars(select(AccountDeletionRecord)))
    for record in records:
        _erase_account_data(database, record.user_id)
    return len(records)
