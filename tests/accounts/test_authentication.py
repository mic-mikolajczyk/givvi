from datetime import timedelta

from flask import Flask
from sqlalchemy import select
from sqlalchemy.orm import Session

from givvi.accounts.security import now
from givvi.models import AccountToken
from givvi.models import LoginSession


def test_verification_is_single_use(api, email_token) -> None:
    assert api("register", {"name": "Bob", "email": "bob@example.com",
               "password": "correct horse battery staple"}).status_code == 202
    token = email_token()

    assert api("verify", {"token": token}).status_code == 200
    replay = api("verify", {"token": token})

    assert replay.status_code == 400
    assert replay.json["code"] == "token_invalid"


def test_unverified_login_is_rejected(api, client) -> None:
    body = {"name": "Bob", "email": "bob@example.com", "password": "correct horse battery staple"}
    api("register", body)

    response = api("login", body)

    assert response.status_code == 403
    assert response.json["code"] == "email_unverified"
    assert client.get("/api/auth/me").status_code == 401


def test_login_rotates_session_and_logout_revokes_it(api, client, verified_user) -> None:
    old_cookie = client.get_cookie("givvi_session").value

    response = api("login", verified_user)

    assert response.status_code == 200
    assert client.get_cookie("givvi_session").value != old_cookie
    assert client.get("/api/auth/me").json["user"]["email"] == verified_user["email"]
    assert api("logout", {}).status_code == 200
    assert client.get("/api/auth/me").status_code == 401


def test_unknown_and_wrong_password_have_same_response(api, verified_user) -> None:
    unknown = api("login", {"email": "unknown@example.com", "password": "incorrect password"})
    wrong = api("login", {"email": verified_user["email"], "password": "incorrect password"})

    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json["code"] == wrong.json["code"] == "invalid_credentials"


def test_reset_revokes_sessions_and_token_cannot_be_reused(api, client, verified_user, email_token) -> None:
    api("login", verified_user)
    assert api("forgot-password", {"email": verified_user["email"]}).status_code == 202
    token = email_token()

    assert api("reset-password", {"token": token, "password": "a new correct password"}).status_code == 200

    assert client.get("/api/auth/me").status_code == 401
    assert api("reset-password", {"token": token, "password": "a newer correct password"}).status_code == 400
    assert api("login", verified_user).status_code == 401
    assert api("login", {"email": verified_user["email"], "password": "a new correct password"}).status_code == 200


def test_expired_tokens_are_rejected(account_app: Flask, api, email_token) -> None:
    api("register", {"name": "Bob", "email": "bob@example.com", "password": "correct horse battery staple"})
    token = email_token()
    with account_app.app_context(), Session(account_app.extensions["database"]) as database, database.begin():
        database.scalar(select(AccountToken)).expires_at = now() - timedelta(seconds=1)

    assert api("verify", {"token": token}).status_code == 400


def test_expired_sessions_are_rejected(account_app: Flask, api, client, verified_user) -> None:
    api("login", verified_user)
    with account_app.app_context(), Session(account_app.extensions["database"]) as database, database.begin():
        for record in database.scalars(select(LoginSession)):
            record.expires_at = now() - timedelta(seconds=1)

    assert client.get("/api/auth/me").status_code == 401


def test_origin_and_csrf_are_enforced(client, verified_user, api) -> None:
    api("login", verified_user)
    token = client.get("/api/auth/csrf").json["csrf_token"]

    response = client.post("/api/auth/logout", json={}, headers={"X-CSRF-Token": token, "Origin": "https://evil.example"})

    assert response.status_code == 403
    assert client.get("/api/auth/me").status_code == 200


def test_rate_limit_is_enforced(account_app: Flask, client) -> None:
    token = client.get("/api/auth/csrf").json["csrf_token"]
    headers = {"X-CSRF-Token": token, "Origin": account_app.config["APP_ORIGIN"]}
    account_app.config["AUTH_RATE_LIMIT"] = 2

    assert client.post("/api/auth/forgot-password",
                       json={"email": "unknown@example.com"}, headers=headers).status_code == 202
    assert client.post("/api/auth/forgot-password",
                       json={"email": "unknown@example.com"}, headers=headers).status_code == 202
    response = client.post("/api/auth/forgot-password", json={"email": "unknown@example.com"}, headers=headers)

    assert response.status_code == 429


def test_resend_invalidates_old_verification_token(api, email_token) -> None:
    api("register", {"name": "Bob", "email": "bob@example.com", "password": "correct horse battery staple"})
    old_token = email_token()

    assert api("resend-verification", {"email": "bob@example.com"}).status_code == 202
    new_token = email_token()

    assert api("verify", {"token": old_token}).status_code == 400
    assert api("verify", {"token": new_token}).status_code == 200


def test_recovery_response_does_not_enumerate_accounts(api, verified_user) -> None:
    known = api("forgot-password", {"email": verified_user["email"]})
    unknown = api("forgot-password", {"email": "unknown@example.com"})

    assert known.status_code == unknown.status_code == 202
    assert known.json["code"] == unknown.json["code"] == "check_email"


def test_session_cookie_defaults_are_secure(account_app: Flask, api, client, verified_user) -> None:
    account_app.config["COOKIE_SECURE"] = True

    response = api("login", verified_user)

    cookie = response.headers["Set-Cookie"]
    assert "Secure" in cookie
    assert "HttpOnly" in cookie
    assert "SameSite=Lax" in cookie


def test_login_rate_limit_uses_normalized_email(account_app: Flask, client, verified_user) -> None:
    token = client.get("/api/auth/csrf").json["csrf_token"]
    headers = {"X-CSRF-Token": token, "Origin": account_app.config["APP_ORIGIN"]}
    account_app.config["AUTH_RATE_LIMIT"] = 2
    statuses = []

    for index, email in enumerate(("ALICE@example.com", " alice@example.com ", "alice@example.com")):
        response = client.post("/api/auth/login", json={"email": email, "password": "incorrect password"},
                               headers=headers, environ_overrides={"REMOTE_ADDR": f"198.51.100.{index + 1}"})
        statuses.append(response.status_code)

    assert statuses == [401, 401, 429]
