import json
from unittest.mock import Mock

from cryptography.fernet import Fernet
from flask import Flask
from sqlalchemy import delete
from sqlalchemy import select
from sqlalchemy.orm import Session

from givvi.mail import deliver_pending
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
