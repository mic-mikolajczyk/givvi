from datetime import datetime
from datetime import timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from givvi.accounts.services import reapply_account_deletions
from givvi.models import AccountDeletionRecord
from givvi.models import AccountToken
from givvi.models import EmailMessage
from givvi.models import Event
from givvi.models import EventAssignment
from givvi.models import EventParticipant
from givvi.models import Gift
from givvi.models import LoginSession
from givvi.models import User
from givvi.models import Wishlist


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


def test_account_deletion_requires_reauthentication_and_cancels_admin_events(
    api, client, account_app, registered_user,
) -> None:
    api("login", registered_user)
    email_change = api("change-email", {
        "email": "pending-deletion@example.com", "current_password": registered_user["password"],
    })
    assert email_change.status_code == 202
    csrf = client.get("/api/auth/csrf").json["csrf_token"]
    headers = {"X-CSRF-Token": csrf, "Origin": account_app.config["APP_ORIGIN"]}
    gift = client.post("/api/wishlist/gifts", json={"name": "Private gift"}, headers=headers)
    assert gift.status_code == 201
    created = client.post("/api/events", json={
        "name": "Winter exchange", "exchange_date": "2026-12-20", "time_zone": "UTC",
    }, headers=headers)
    event_id = created.json["event"]["id"]
    user_id = client.get("/api/auth/me").json["user"]["id"]
    for index in range(3):
        participant = client.post(f"/api/events/{event_id}/participants", json={"name": f"Member {index}"},
                                  headers=headers)
        assert participant.status_code == 201
    invitation = client.post(f"/api/events/{event_id}/invitations", json={"email": "unregistered@example.com"},
                             headers=headers)
    assert invitation.status_code == 202
    drawing = client.post(f"/api/events/{event_id}/drawing", json={}, headers=headers)
    assert drawing.status_code == 200

    wrong_password = client.delete("/api/auth/account", json={"current_password": "wrong password"}, headers=headers)
    blocked = client.delete("/api/auth/account", json={
        "current_password": registered_user["password"],
    }, headers=headers)

    assert wrong_password.status_code == 401
    assert blocked.status_code == 409
    cancelled = client.post(f"/api/events/{event_id}/cancel", headers=headers)
    assert cancelled.status_code == 200
    deleted = client.delete("/api/auth/account", json={
        "current_password": registered_user["password"],
    }, headers=headers)

    assert deleted.status_code == 200
    assert client.get("/api/auth/me").status_code == 401
    with Session(account_app.extensions["database"]) as database:
        assert database.scalar(select(User).where(User.email == registered_user["email"])) is None
        assert database.scalar(select(Wishlist).where(Wishlist.user_id == user_id)) is None
        assert database.scalar(select(Gift).where(Gift.wishlist_id == user_id)) is None
        assert database.scalar(select(AccountToken).where(AccountToken.user_id == user_id)) is None
        assert database.scalar(select(EmailMessage).where(EmailMessage.user_id == user_id)) is None
        assert database.scalar(select(EmailMessage).where(EmailMessage.user_id.is_(None))) is None
        event = database.get(Event, event_id)
        assert event is not None
        assert event.admin_id is None
        assert event.cancelled is True
        assert database.scalar(select(EventAssignment.draw_id).where(EventAssignment.event_id == event_id)) is not None
        assert database.scalar(select(LoginSession).where(LoginSession.user_id.is_not(None))) is None


def test_restore_reapplies_account_deletion_records(account_app) -> None:
    user_id = "restored-user-id"
    with Session(account_app.extensions["database"]) as database, database.begin():
        user = User(
            id=user_id,
            name="Restored personal name",
            email="restored@example.com",
            password_hash="unused",
            language="en",
        )
        database.add(user)
        database.add(Wishlist(user_id=user_id))
        event = Event(
            admin_id=user_id,
            name="Restored event",
            exchange_date=datetime(2026, 12, 20).date(),
            time_zone="UTC",
            currency="EUR",
        )
        database.add(event)
        database.flush()
        participant = EventParticipant(event_id=event.id, name="Restored roster name", user_id=user_id)
        database.add(participant)
        database.add(AccountDeletionRecord(user_id=user_id, deleted_at=datetime(2026, 10, 26, tzinfo=timezone.utc)))
        database.flush()
        event_id = event.id
        participant_id = participant.id

    with Session(account_app.extensions["database"]) as database, database.begin():
        assert reapply_account_deletions(database) == 1
    with Session(account_app.extensions["database"]) as database, database.begin():
        assert database.get(User, user_id) is None
        assert database.get(Wishlist, user_id) is None
        event = database.get(Event, event_id)
        participant = database.get(EventParticipant, participant_id)
        assert event.admin_id is None
        assert event.cancelled is True
        assert participant.name == "Deleted user"
        assert participant.user_id is None
        assert reapply_account_deletions(database) == 1
