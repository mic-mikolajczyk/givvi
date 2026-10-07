def test_profile_update_uses_verified_identity(api, client, verified_user) -> None:
    api("login", verified_user)

    response = api("profile", {"name": "Alicja", "language": "pl"})

    assert response.status_code == 200
    assert client.get("/api/auth/me").json["user"]["name"] == "Alicja"
    assert client.get("/api/auth/me").json["user"]["language"] == "pl"


def test_password_change_requires_current_password(api, client, verified_user) -> None:
    api("login", verified_user)

    rejected = api("change-password", {"current_password": "wrong password", "password": "a new correct password"})
    accepted = api("change-password", {"current_password": verified_user["password"], "password": "a new correct password"})

    assert rejected.status_code == 401
    assert accepted.status_code == 200
    assert client.get("/api/auth/me").status_code == 401


def test_email_change_waits_for_verification(api, client, verified_user, email_token) -> None:
    api("login", verified_user)

    response = api("change-email", {"email": "new@example.com", "current_password": verified_user["password"]})

    assert response.status_code == 202
    assert client.get("/api/auth/me").json["user"]["email"] == verified_user["email"]
    assert api("verify", {"token": email_token()}).status_code == 200
    assert client.get("/api/auth/me").status_code == 401
    assert api("login", {"email": "new@example.com", "password": verified_user["password"]}).status_code == 200


def test_password_change_clears_unconfirmed_email(api, client, verified_user) -> None:
    api("login", verified_user)
    assert api("change-email", {"email": "pending@example.com", "current_password": verified_user["password"]}).status_code == 202

    assert api("change-password", {"current_password": verified_user["password"], "password": "a new correct password"}).status_code == 200
    assert api("login", {"email": verified_user["email"], "password": "a new correct password"}).status_code == 200

    assert client.get("/api/auth/me").json["user"]["pending_email"] is None
