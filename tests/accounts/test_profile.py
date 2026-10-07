def test_profile_update_uses_authenticated_identity(api, client, registered_user) -> None:
    api("login", registered_user)

    response = api("profile", {"name": "Alicja", "language": "pl"})

    assert response.status_code == 200
    assert client.get("/api/auth/me").json["user"]["name"] == "Alicja"
    assert client.get("/api/auth/me").json["user"]["language"] == "pl"


def test_password_change_requires_current_password(api, client, registered_user) -> None:
    api("login", registered_user)

    rejected = api("change-password", {"current_password": "wrong password", "password": "a new correct password"})
    accepted = api("change-password",
                   {"current_password": registered_user["password"], "password": "a new correct password"})

    assert rejected.status_code == 401
    assert accepted.status_code == 200
    assert client.get("/api/auth/me").status_code == 401


def test_email_change_waits_for_verification(api, client, registered_user, email_token) -> None:
    api("login", registered_user)

    response = api("change-email", {"email": "new@example.com", "current_password": registered_user["password"]})

    assert response.status_code == 202
    assert client.get("/api/auth/me").json["user"]["email"] == registered_user["email"]
    assert api("verify", {"token": email_token()}).status_code == 200
    assert client.get("/api/auth/me").status_code == 401
    assert api("login", {"email": "new@example.com", "password": registered_user["password"]}).status_code == 200


def test_password_change_clears_unconfirmed_email(api, client, registered_user) -> None:
    api("login", registered_user)
    assert api("change-email", {"email": "pending@example.com",
               "current_password": registered_user["password"]}).status_code == 202

    assert api("change-password",
               {"current_password": registered_user["password"], "password": "a new correct password"}).status_code == 200
    assert api("login", {"email": registered_user["email"], "password": "a new correct password"}).status_code == 200

    assert client.get("/api/auth/me").json["user"]["pending_email"] is None
