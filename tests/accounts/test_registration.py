import json

from cryptography.fernet import Fernet
from flask import Flask
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from givvi.models import EmailMessage
from givvi.models import User
from givvi.models import Wishlist

PASSWORD = "correct horse battery staple"
ORIGIN = "http://127.0.0.1:5173"


def test_registration_creates_one_wishlist_and_encrypted_email(account_app: Flask) -> None:
    client = account_app.test_client()
    csrf = client.get("/api/auth/csrf").json["csrf_token"]

    response = client.post("/api/auth/register", json={
        "name": "Alicja", "email": "ALICJA@example.com", "password": PASSWORD, "language": "pl",
    }, headers={"X-CSRF-Token": csrf, "Origin": ORIGIN})

    assert response.status_code == 202
    with Session(account_app.extensions["database"]) as database:
        user = database.scalar(select(User))
        assert user.email == "alicja@example.com"
        assert user.password_hash.startswith("$argon2id$")
        assert PASSWORD not in user.password_hash
        assert len(database.scalars(select(Wishlist)).all()) == 1
        message = database.scalar(select(EmailMessage))
        assert "alicja@example.com" not in message.payload
        payload = Fernet(account_app.config["OUTBOX_KEY"].encode()).decrypt(message.payload.encode()).decode()
        assert "Potwierdź" in payload


def test_duplicate_registration_has_same_response_and_no_extra_rows(account_app: Flask) -> None:
    client = account_app.test_client()
    csrf = client.get("/api/auth/csrf").json["csrf_token"]
    body = {"name": "Alice", "email": "alice@example.com", "password": PASSWORD, "language": "en"}

    first = client.post("/api/auth/register", json=body, headers={"X-CSRF-Token": csrf, "Origin": ORIGIN})
    second = client.post("/api/auth/register", json=body, headers={"X-CSRF-Token": csrf, "Origin": ORIGIN})

    assert first.status_code == second.status_code == 202
    assert first.json["code"] == second.json["code"]
    with Session(account_app.extensions["database"]) as database:
        assert len(database.scalars(select(User)).all()) == 1
        assert len(database.scalars(select(Wishlist)).all()) == 1
        assert len(database.scalars(select(EmailMessage)).all()) == 1


def test_registration_requires_csrf(account_app: Flask) -> None:
    response = account_app.test_client().post("/api/auth/register", json={})

    assert response.status_code == 403
    assert response.json["code"] == "csrf_invalid"


def test_registration_rolls_back_if_email_queueing_fails(account_app: Flask, monkeypatch, caplog) -> None:
    from givvi.accounts import services

    def fail_queue(*arguments) -> None:
        raise OSError("private_queue_credential")

    monkeypatch.setattr(services, "token_email", fail_queue)
    client = account_app.test_client()
    csrf = client.get("/api/auth/csrf").json["csrf_token"]

    response = client.post("/api/auth/register", json={
        "name": "Alice", "email": "alice@example.com", "password": PASSWORD,
    }, headers={"X-CSRF-Token": csrf, "Origin": ORIGIN})

    assert response.status_code == 500
    assert response.json["code"] == "internal_error"
    with Session(account_app.extensions["database"]) as database:
        assert database.scalars(select(User)).all() == []
        assert database.scalars(select(Wishlist)).all() == []
        assert database.scalars(select(EmailMessage)).all() == []
    assert "private_queue_credential" not in caplog.text
    assert "private_queue_credential" not in json.dumps([record.__dict__ for record in caplog.records], default=str)
    assert "private_queue_credential" not in response.get_data(as_text=True)


@pytest.mark.parametrize("password", ["short", "x" * 129])
def test_password_bounds_are_enforced(account_app: Flask, password: str) -> None:
    client = account_app.test_client()
    csrf = client.get("/api/auth/csrf").json["csrf_token"]

    response = client.post("/api/auth/register", json={
        "name": "Alice", "email": "alice@example.com", "password": password,
    }, headers={"X-CSRF-Token": csrf, "Origin": ORIGIN})

    assert response.status_code == 422
    assert response.json["field_errors"]["password"] == "password_length"
