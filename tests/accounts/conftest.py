import json
from urllib.parse import parse_qs
from urllib.parse import urlsplit

from cryptography.fernet import Fernet
from flask import Flask
import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from givvi.models import EmailMessage


@pytest.fixture
def client(account_app: Flask):
    return account_app.test_client()


@pytest.fixture
def api(client, account_app: Flask):
    def post(path: str, body: dict):
        token = client.get("/api/auth/csrf").json["csrf_token"]
        return client.post(f"/api/auth/{path}", json=body, headers={
            "X-CSRF-Token": token, "Origin": account_app.config["APP_ORIGIN"],
        })
    return post


@pytest.fixture
def email_payload(account_app: Flask):
    def payload():
        with Session(account_app.extensions["database"]) as database:
            message = database.scalars(select(EmailMessage).order_by(EmailMessage.available_at.desc())).first()
            return json.loads(Fernet(account_app.config["OUTBOX_KEY"].encode()).decrypt(message.payload.encode()))
    return payload


@pytest.fixture
def email_token(email_payload):
    def token():
        link = email_payload()["body"].splitlines()[-1]
        return parse_qs(urlsplit(link).fragment)["token"][0]
    return token


@pytest.fixture
def verified_user(api, email_token):
    body = {"name": "Alice", "email": "alice@example.com", "password": "correct horse battery staple", "language": "en"}
    assert api("register", body).status_code == 202
    assert api("verify", {"token": email_token()}).status_code == 200
    return body
