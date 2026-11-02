from datetime import datetime
from datetime import timedelta
from datetime import timezone
import json
from unittest.mock import Mock

from cryptography.fernet import Fernet
from flask import Flask
from sqlalchemy import delete
from sqlalchemy import select
from sqlalchemy.orm import Session

from givvi.mail import deliver_pending
from givvi.mail import MAX_DELIVERY_ATTEMPTS
from givvi.models import AccountToken
from givvi.models import EmailMessage


def test_worker_sends_committed_email_and_purges_payload(account_app: Flask, api) -> None:
    api("register", {"name": "Alice", "email": "alice@example.com", "password": "correct horse battery staple"})
    api("forgot-password", {"email": "alice@example.com"})
    sender = Mock()

    delivered = deliver_pending(account_app, sender)

    assert delivered == 1
    assert sender.call_args.args[0]["to"] == "alice@example.com"
    with Session(account_app.extensions["database"]) as database:
        message = database.scalar(select(EmailMessage))
        assert message.delivered_at is not None
        assert message.payload is None


def test_provider_failure_keeps_encrypted_payload_for_retry(account_app: Flask, api, caplog) -> None:
    api("register", {"name": "Alice", "email": "alice@example.com", "password": "correct horse battery staple"})
    api("forgot-password", {"email": "alice@example.com"})
    sender = Mock(side_effect=OSError("private provider credential"))

    assert deliver_pending(account_app, sender) == 0

    with Session(account_app.extensions["database"]) as database:
        message = database.scalar(select(EmailMessage))
        assert message.attempts == 1
        assert message.delivered_at is None
        assert "alice@example.com" not in message.payload
        payload = json.loads(Fernet(account_app.config["OUTBOX_KEY"].encode()).decrypt(message.payload.encode()))
        assert payload["to"] == "alice@example.com"
    assert "private provider credential" not in caplog.text


def test_worker_discards_invalidated_account_email(account_app: Flask, api) -> None:
    api("register", {"name": "Alice", "email": "alice@example.com", "password": "correct horse battery staple"})
    api("forgot-password", {"email": "alice@example.com"})
    with Session(account_app.extensions["database"]) as database, database.begin():
        database.execute(delete(AccountToken))
    sender = Mock()

    assert deliver_pending(account_app, sender) == 0

    sender.assert_not_called()
    with Session(account_app.extensions["database"]) as database:
        message = database.scalar(select(EmailMessage))
        assert message.failed_at is not None
        assert message.payload is None


def test_retry_waits_and_exhaustion_alerts_without_private_data(account_app: Flask, api, caplog) -> None:
    instant = datetime(2026, 10, 28, tzinfo=timezone.utc)
    account_app.config["CLOCK"] = lambda: instant
    api("register", {"name": "Alice", "email": "alice@example.com", "password": "correct horse battery staple"})
    api("forgot-password", {"email": "alice@example.com"})
    sender = Mock(side_effect=OSError("private provider credential"))

    for attempt in range(MAX_DELIVERY_ATTEMPTS):
        assert deliver_pending(account_app, sender) == 0
        with Session(account_app.extensions["database"]) as database:
            message = database.scalar(select(EmailMessage))
            assert message.attempts == attempt + 1
            if attempt < MAX_DELIVERY_ATTEMPTS - 1:
                available = message.available_at.replace(tzinfo=timezone.utc)
                delay = (available - instant).total_seconds()
                assert 30 * 2 ** attempt <= delay <= 30 * 2 ** attempt + 30
                assert deliver_pending(account_app, sender) == 0
                instant = available
    assert sender.call_count == MAX_DELIVERY_ATTEMPTS
    with Session(account_app.extensions["database"]) as database:
        message = database.scalar(select(EmailMessage))
        assert message.failed_at is not None
        assert message.payload is None
    assert "Email delivery exhausted" in caplog.text
    assert "private provider credential" not in caplog.text
    assert "alice@example.com" not in caplog.text


def test_worker_recovers_expired_but_not_live_lease(account_app: Flask, api) -> None:
    instant = datetime(2026, 10, 28, tzinfo=timezone.utc)
    account_app.config["CLOCK"] = lambda: instant
    api("register", {"name": "Alice", "email": "alice@example.com", "password": "correct horse battery staple"})
    api("forgot-password", {"email": "alice@example.com"})
    with Session(account_app.extensions["database"]) as database, database.begin():
        message = database.scalar(select(EmailMessage))
        message.lease_id = "crashed-worker"
        message.lease_until = instant + timedelta(seconds=60)
        message.attempts = 1
    sender = Mock()

    assert deliver_pending(account_app, sender) == 0
    instant += timedelta(seconds=61)
    assert deliver_pending(account_app, sender) == 1

    assert sender.call_count == 1
    with Session(account_app.extensions["database"]) as database:
        message = database.scalar(select(EmailMessage))
        assert message.attempts == 2
        assert message.lease_id is None
        assert message.payload is None


def test_worker_prunes_terminal_rows_but_preserves_pending_mail(account_app: Flask, api) -> None:
    instant = datetime(2026, 10, 28, tzinfo=timezone.utc)
    account_app.config["CLOCK"] = lambda: instant
    api("register", {"name": "Alice", "email": "alice@example.com", "password": "correct horse battery staple"})
    api("forgot-password", {"email": "alice@example.com"})
    with Session(account_app.extensions["database"]) as database, database.begin():
        pending = database.scalar(select(EmailMessage))
        pending.available_at = instant + timedelta(minutes=5)
        for terminal_field in ("delivered_at", "failed_at"):
            database.add(EmailMessage(
                payload=None,
                available_at=instant - timedelta(days=8),
                expires_at=instant - timedelta(days=7),
                **{terminal_field: instant - timedelta(days=8)},
            ))

    assert deliver_pending(account_app, Mock()) == 0

    with Session(account_app.extensions["database"]) as database:
        messages = database.scalars(select(EmailMessage)).all()
        assert len(messages) == 1
        assert messages[0].payload is not None


def test_crashed_final_attempt_is_not_sent_again(account_app: Flask, api, caplog) -> None:
    instant = datetime(2026, 10, 28, tzinfo=timezone.utc)
    account_app.config["CLOCK"] = lambda: instant
    api("register", {"name": "Alice", "email": "alice@example.com", "password": "correct horse battery staple"})
    api("forgot-password", {"email": "alice@example.com"})
    with Session(account_app.extensions["database"]) as database, database.begin():
        message = database.scalar(select(EmailMessage))
        message.attempts = MAX_DELIVERY_ATTEMPTS
        message.lease_id = "crashed-worker"
        message.lease_until = instant - timedelta(seconds=1)
    sender = Mock()

    assert deliver_pending(account_app, sender) == 0

    sender.assert_not_called()
    with Session(account_app.extensions["database"]) as database:
        message = database.scalar(select(EmailMessage))
        assert message.failed_at is not None
        assert message.payload is None
    assert "Email delivery exhausted" in caplog.text
