from collections.abc import Callable
from datetime import timedelta
from email.message import EmailMessage as SmtpMessage
import json
import smtplib
import ssl
from urllib.parse import parse_qs
from urllib.parse import urlsplit
from uuid import uuid4

from cryptography.fernet import Fernet
from cryptography.fernet import InvalidToken
from flask import current_app
from flask import Flask
from sqlalchemy import delete
from sqlalchemy import or_
from sqlalchemy import select
from sqlalchemy import update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from givvi.accounts.security import digest
from givvi.accounts.security import now
from givvi.accounts.security import utc
from givvi.models import AccountToken
from givvi.models import EmailMessage
from givvi.models import LoginSession
from givvi.models import RateBucket

MAX_DELIVERY_ATTEMPTS = 5
LEASE_SECONDS = 60
SMTP_TIMEOUT_SECONDS = 10
RETRY_BASE_SECONDS = 30


def account_link_is_active(engine: Engine, payload: dict) -> bool:
    link = urlsplit(payload["body"].splitlines()[-1])
    if link.path not in ("/verify", "/reset-password"):
        return True
    token = parse_qs(link.fragment).get("token", [""])[0]
    with Session(engine) as database:
        record = database.get(AccountToken, digest(token))
        return bool(record and record.purpose in ("reset", "email") and utc(record.expires_at) > now())


def send_smtp(payload: dict) -> None:
    message = SmtpMessage()
    message["From"] = current_app.config["SMTP_FROM"]
    message["To"] = payload["to"]
    message["Subject"] = payload["subject"]
    message.set_content(payload["body"])
    with smtplib.SMTP(
        current_app.config["SMTP_HOST"], current_app.config["SMTP_PORT"], timeout=SMTP_TIMEOUT_SECONDS
    ) as smtp:
        if current_app.config["SMTP_TLS"]:
            smtp.starttls(context=ssl.create_default_context())
        if current_app.config.get("SMTP_USERNAME"):
            smtp.login(current_app.config["SMTP_USERNAME"], current_app.config["SMTP_PASSWORD"])
        smtp.send_message(message)


def deliver_pending(app: Flask, sender: Callable[[dict], None] | None = None, limit: int = 20) -> int:
    delivered = 0
    with app.app_context():
        engine = app.extensions["database"]
        with Session(engine) as database, database.begin():
            expired = update(EmailMessage).where(EmailMessage.expires_at <= now(), EmailMessage.payload.is_not(None))
            database.execute(expired.values(
                payload=None, failed_at=now(), lease_id=None, lease_until=None,
            ))
            for model in (AccountToken, LoginSession, RateBucket):
                database.execute(delete(model).where(model.expires_at <= now()))
        for unused_index in range(limit):
            with Session(engine) as database, database.begin():
                record = database.scalar(select(EmailMessage).where(
                    EmailMessage.payload.is_not(None),
                    EmailMessage.delivered_at.is_(None),
                    EmailMessage.failed_at.is_(None),
                    EmailMessage.available_at <= now(),
                    EmailMessage.expires_at > now(),
                    or_(EmailMessage.lease_until.is_(None),
                    EmailMessage.lease_until <= now()),
                ).order_by(EmailMessage.available_at).with_for_update(skip_locked=True).limit(1))
                if not record:
                    break
                record.lease_id = str(uuid4())
                record.lease_until = now() + timedelta(seconds=LEASE_SECONDS)
                record.attempts += 1
                identifier, lease, encrypted, attempts = record.id, record.lease_id, record.payload, record.attempts
            failed = False
            permanent = False
            try:
                payload = json.loads(Fernet(app.config["OUTBOX_KEY"].encode()).decrypt(encrypted.encode()))
                if account_link_is_active(engine, payload):
                    (sender or send_smtp)(payload)
                else:
                    app.logger.info("Obsolete account email discarded")
                    failed = permanent = True
            except (smtplib.SMTPException, OSError, InvalidToken, ValueError, KeyError) as error:
                app.logger.warning("Email delivery failed", extra={"error_type": type(error).__name__})
                failed = True
                permanent = isinstance(error, (InvalidToken, ValueError, KeyError)) or attempts >= MAX_DELIVERY_ATTEMPTS
            with Session(engine) as database, database.begin():
                record = database.scalar(select(EmailMessage).where(EmailMessage.id == identifier,
                                         EmailMessage.lease_id == lease).with_for_update())
                if not record:
                    continue
                record.lease_id = None
                record.lease_until = None
                if not failed:
                    record.delivered_at = now()
                    record.payload = None
                    delivered += 1
                elif permanent:
                    record.failed_at = now()
                    record.payload = None
                else:
                    record.available_at = now() + timedelta(seconds=RETRY_BASE_SECONDS * 2 ** (attempts - 1))
    return delivered
