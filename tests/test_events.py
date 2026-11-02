from datetime import date
from datetime import datetime
from datetime import timezone
import json
from urllib.parse import parse_qs
from urllib.parse import urlsplit

from cryptography.fernet import Fernet
import pytest
from sqlalchemy import event as sqlalchemy_event
from sqlalchemy import select
from sqlalchemy.orm import Session

from givvi.accounts.security import COOKIE_NAME
from givvi.accounts.security import digest
from givvi.mail import deliver_pending
from givvi.models import EmailMessage
from givvi.models import Event
from givvi.models import EventAssignment
from givvi.models import EventDraw
from givvi.models import EventParticipant
from givvi.models import User


def register(client, app, email: str, name: str = "Alice", language: str = "en") -> str:
    csrf = client.get("/api/auth/csrf").json["csrf_token"]
    response = client.post("/api/auth/register", json={
        "name": name, "email": email, "password": "correct horse battery staple", "language": language,
    }, headers={"X-CSRF-Token": csrf, "Origin": app.config["APP_ORIGIN"]})
    assert response.status_code == 201
    return response.json["csrf_token"]


def post(client, app, csrf: str, path: str, body: dict):
    return client.post(path, json=body, headers={"X-CSRF-Token": csrf, "Origin": app.config["APP_ORIGIN"]})


def create_event(client, app, csrf: str, name: str = "Winter exchange"):
    return post(client, app, csrf, "/api/events", {
        "name": name, "exchange_date": "2026-12-20", "time_zone": "Europe/Warsaw",
    })


def create_claimed_event(account_app, count: int, email_prefix: str):
    admin = account_app.test_client()
    admin_csrf = register(admin, account_app, f"{email_prefix}-admin@example.com")
    event_id = create_event(admin, account_app, admin_csrf).json["event"]["id"]
    participant_ids = []
    for index in range(count):
        participant = post(admin, account_app, admin_csrf, f"/api/events/{event_id}/participants", {
            "name": f"Member {index}",
        })
        participant_ids.append(participant.json["participant"]["id"])
    link = post(admin, account_app, admin_csrf, f"/api/events/{event_id}/invite-link", {}).json["link"]
    token = parse_qs(urlsplit(link).fragment)["token"][0]
    for index, participant_id in enumerate(participant_ids):
        member = account_app.test_client()
        member_csrf = register(member, account_app, f"{email_prefix}-{index}@example.com")
        claimed = post(member, account_app, member_csrf, f"/api/events/{event_id}/claim", {
            "participant_id": participant_id, "token": token,
        })
        assert claimed.status_code == 200
    return admin, admin_csrf, event_id, participant_ids


def test_authenticated_user_creates_private_event(account_app) -> None:
    client = account_app.test_client()
    csrf = register(client, account_app, "alice@example.com")

    response = post(client, account_app, csrf, "/api/events", {
        "name": "Winter exchange", "exchange_date": "2026-12-20", "time_zone": "Europe/Warsaw",
        "currency": "EUR", "budget": "35.50",
    })

    assert response.status_code == 201
    event = response.json["event"]
    assert event["name"] == "Winter exchange"
    assert event["exchange_date"] == date(2026, 12, 20).isoformat()
    assert event["time_zone"] == "Europe/Warsaw"
    assert event["currency"] == "EUR"
    assert event["budget"] == "35.50"
    assert event["is_admin"] is True
    assert client.get("/api/events").json["events"] == [event]

    client.delete_cookie(COOKIE_NAME)
    assert client.get("/api/events").status_code == 401


def test_conditional_event_reads_recheck_access_and_change_with_roster(account_app) -> None:
    admin = account_app.test_client()
    csrf = register(admin, account_app, "conditional-admin@example.com")
    event_id = create_event(admin, account_app, csrf).json["event"]["id"]
    path = f"/api/events/{event_id}"
    first = admin.get(path)

    assert first.headers.get("ETag")
    etag = first.headers["ETag"]
    unchanged = admin.get(path, headers={"If-None-Match": etag})
    assert unchanged.status_code == 304
    assert unchanged.data == b""
    assert unchanged.headers["Cache-Control"] == "no-store"
    post(admin, account_app, csrf, f"{path}/participants", {"name": "New member"})
    updated = admin.get(path, headers={"If-None-Match": etag})
    assert updated.status_code == 200
    assert updated.headers["ETag"] != etag
    outsider = account_app.test_client()
    register(outsider, account_app, "conditional-outsider@example.com")
    assert outsider.get(path, headers={"If-None-Match": updated.headers["ETag"]}).status_code == 404
    admin.delete_cookie(COOKIE_NAME)
    assert admin.get(path, headers={"If-None-Match": etag}).status_code == 401


def test_invitation_secrets_never_receive_conditional_validators(account_app) -> None:
    admin = account_app.test_client()
    csrf = register(admin, account_app, "secret-cache@example.com")
    event_id = create_event(admin, account_app, csrf).json["event"]["id"]
    path = f"/api/events/{event_id}/invite-link"
    post(admin, account_app, csrf, path, {})

    response = admin.get(path)

    assert response.status_code == 200
    assert "ETag" not in response.headers
    assert response.headers["Cache-Control"] == "no-store"


def test_recipient_get_requires_an_existing_reveal_and_is_never_cached(account_app) -> None:
    admin, csrf, event_id, participant_ids = create_claimed_event(account_app, 3, "recipient-read")
    post(admin, account_app, csrf, f"/api/events/{event_id}/drawing", {})
    member = account_app.test_client()
    login_csrf = member.get("/api/auth/csrf").json["csrf_token"]
    login = post(member, account_app, login_csrf, "/api/auth/login", {
        "email": "recipient-read-0@example.com", "password": "correct horse battery staple",
    })
    path = f"/api/events/{event_id}/reveal"

    assert member.get(path).status_code == 404
    assert admin.get(path).status_code == 404
    revealed = post(member, account_app, login.json["csrf_token"], path, {})
    retrieved = member.get(path)

    assert retrieved.status_code == 200
    assert retrieved.json == revealed.json
    assert "ETag" not in retrieved.headers
    assert retrieved.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize("event_count", [1, 10])
def test_event_listing_query_count_is_bounded(account_app, event_count: int) -> None:
    admin = account_app.test_client()
    csrf = register(admin, account_app, "query-count@example.com")
    for index in range(event_count):
        event_id = create_event(admin, account_app, csrf, f"Exchange {index}").json["event"]["id"]
        post(admin, account_app, csrf, f"/api/events/{event_id}/participants", {"name": "Roster member"})
    statements = []

    def count_query(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    engine = account_app.extensions["database"]
    sqlalchemy_event.listen(engine, "before_cursor_execute", count_query)
    try:
        response = admin.get("/api/events")
    finally:
        sqlalchemy_event.remove(engine, "before_cursor_execute", count_query)

    assert response.status_code == 200
    assert len(response.json["events"]) == event_count
    assert all(len(entry["participants"]) == 1 for entry in response.json["events"])
    assert len(statements) <= 6


@pytest.mark.parametrize(("field", "value"), [
    ("exchange_date", "not-a-date"),
    ("time_zone", "Mars/Olympus"),
    ("exchange_time", "02:30"),
    ("currency", "USD"),
    ("budget", "1000000.00"),
    ("budget", "1.001"),
])
def test_event_creation_rejects_invalid_values(account_app, field: str, value: str) -> None:
    client = account_app.test_client()
    csrf = register(client, account_app, f"{field}-{value.replace(':', '-')}@example.com")
    body = {"name": "Winter exchange", "exchange_date": "2026-12-20", "time_zone": "Europe/Warsaw"}
    if field == "exchange_time":
        body.update(exchange_date="2026-03-29", time_zone="Europe/Warsaw")
    body[field] = value

    response = post(client, account_app, csrf, "/api/events", body)

    assert response.status_code == 400
    assert field in response.json["field_errors"]
    assert client.get("/api/events").json["events"] == []


def test_event_currency_defaults_to_users_language(account_app) -> None:
    client = account_app.test_client()
    csrf = register(client, account_app, "ola@example.com", "Ola", "pl")

    response = create_event(client, account_app, csrf)

    assert response.status_code == 201
    assert response.json["event"]["currency"] == "PLN"


def test_event_rejects_ambiguous_local_time(account_app) -> None:
    client = account_app.test_client()
    csrf = register(client, account_app, "ambiguous@example.com")

    response = post(client, account_app, csrf, "/api/events", {
        "name": "Autumn exchange", "exchange_date": "2026-10-25", "exchange_time": "02:30",
        "time_zone": "Europe/Warsaw",
    })

    assert response.status_code == 400
    assert response.json["field_errors"]["exchange_time"] == "ambiguous_local_time"


def test_admin_manages_unclaimed_roster_and_other_users_cannot_access_event(account_app) -> None:
    admin = account_app.test_client()
    csrf = register(admin, account_app, "admin@example.com")
    created = create_event(admin, account_app, csrf)
    event_id = created.json["event"]["id"]

    added = post(admin, account_app, csrf, f"/api/events/{event_id}/participants", {"name": "  Morgan  "})
    assert added.status_code == 201
    participant = added.json["participant"]
    assert participant["name"] == "Morgan"
    assert participant["claimed"] is False
    assert created.json["event"]["participants"] == []

    renamed = admin.patch(f"/api/events/{event_id}/participants/{participant['id']}", json={"name": "Morgan Lee"},
                          headers={"X-CSRF-Token": csrf, "Origin": account_app.config["APP_ORIGIN"]})
    assert renamed.status_code == 200
    assert renamed.json["participant"]["name"] == "Morgan Lee"
    assert admin.get(f"/api/events/{event_id}").json["event"]["participants"] == [
        {"id": participant["id"], "name": "Morgan Lee", "claimed": False},
    ]

    attendee = account_app.test_client()
    attendee_csrf = register(attendee, account_app, "attendee@example.com", "Taylor")
    assert attendee.get(f"/api/events/{event_id}").status_code == 404
    denied = post(attendee, account_app, attendee_csrf, f"/api/events/{event_id}/participants", {"name": "Nope"})
    assert denied.status_code == 404

    removed = admin.delete(f"/api/events/{event_id}/participants/{participant['id']}", headers={
        "X-CSRF-Token": csrf, "Origin": account_app.config["APP_ORIGIN"],
    })
    assert removed.status_code == 200
    assert admin.get(f"/api/events/{event_id}").json["event"]["participants"] == []


@pytest.mark.parametrize("read_only_state", ["archived", "cancelled", "drawing_enabled"])
def test_event_edit_and_roster_mutation_reject_read_only_state(account_app, read_only_state: str) -> None:
    client = account_app.test_client()
    csrf = register(client, account_app, "owner@example.com")
    event_id = create_event(client, account_app, csrf).json["event"]["id"]
    with Session(account_app.extensions["database"]) as database, database.begin():
        event = database.get(Event, event_id)
        if read_only_state == "archived":
            event.archived = True
        elif read_only_state == "cancelled":
            event.cancelled = True
        else:
            event.drawing_enabled = True
            event.drawing_ever_enabled = True

    headers = {"X-CSRF-Token": csrf, "Origin": account_app.config["APP_ORIGIN"]}
    event_update = client.patch(f"/api/events/{event_id}", json={"name": "Changed"}, headers=headers)
    roster_add = client.post(f"/api/events/{event_id}/participants", json={"name": "Morgan"}, headers=headers)

    assert event_update.status_code == 409
    assert roster_add.status_code == 409


def test_event_lifecycle_archive_cancel_and_delete_rules(account_app) -> None:
    client = account_app.test_client()
    csrf = register(client, account_app, "lifecycle@example.com")
    event_id = create_event(client, account_app, csrf).json["event"]["id"]
    headers = {"X-CSRF-Token": csrf, "Origin": account_app.config["APP_ORIGIN"]}

    archived = client.post(f"/api/events/{event_id}/archive", headers=headers)

    assert archived.status_code == 200
    assert archived.json["event"]["archived"] is True
    assert client.patch(f"/api/events/{event_id}", json={"name": "Changed"}, headers=headers).status_code == 409

    unarchived = client.delete(f"/api/events/{event_id}/archive", headers=headers)

    assert unarchived.status_code == 200
    assert unarchived.json["event"]["archived"] is False

    cancelled = client.post(f"/api/events/{event_id}/cancel", headers=headers)

    assert cancelled.status_code == 200
    assert cancelled.json["event"]["cancelled"] is True
    assert client.delete(f"/api/events/{event_id}/archive", headers=headers).status_code == 409
    assert client.delete(f"/api/events/{event_id}", headers=headers).status_code == 200


def test_event_delete_requires_draw_to_be_reset(account_app) -> None:
    admin, csrf, event_id, _ = create_claimed_event(account_app, 3, "lifecycle-draw")
    headers = {"X-CSRF-Token": csrf, "Origin": account_app.config["APP_ORIGIN"]}

    enabled = post(admin, account_app, csrf, f"/api/events/{event_id}/drawing", {})
    assert enabled.status_code == 200
    assert admin.delete(f"/api/events/{event_id}", headers=headers).status_code == 409

    reset = admin.delete(f"/api/events/{event_id}/drawing", headers=headers)
    assert reset.status_code == 200
    assert admin.delete(f"/api/events/{event_id}", headers=headers).status_code == 200


def test_admin_transfers_ownership_to_claimed_participant(account_app) -> None:
    admin = account_app.test_client()
    admin_csrf = register(admin, account_app, "transfer-admin@example.com")
    event_id = create_event(admin, account_app, admin_csrf).json["event"]["id"]
    participant_id = post(admin, account_app, admin_csrf, f"/api/events/{event_id}/participants", {
        "name": "Member",
    }).json["participant"]["id"]
    invite_link = post(admin, account_app, admin_csrf, f"/api/events/{event_id}/invite-link", {}).json["link"]
    token = parse_qs(urlsplit(invite_link).fragment)["token"][0]
    member = account_app.test_client()
    member_csrf = register(member, account_app, "transfer-member@example.com")
    assert post(member, account_app, member_csrf, f"/api/events/{event_id}/claim", {
        "participant_id": participant_id, "token": token,
    }).status_code == 200
    headers = {"X-CSRF-Token": admin_csrf, "Origin": account_app.config["APP_ORIGIN"]}
    member_transfer = post(member, account_app, member_csrf, f"/api/events/{event_id}/transfer", {
        "participant_id": participant_id,
    })
    assert member_transfer.status_code == 403

    transferred = admin.post(f"/api/events/{event_id}/transfer", json={"participant_id": participant_id},
                             headers=headers)

    assert transferred.status_code == 200
    assert transferred.json["event"]["is_admin"] is False
    assert member.get(f"/api/events/{event_id}").json["event"]["is_admin"] is True
    assert admin.post(f"/api/events/{event_id}/participants", json={"name": "No longer admin"},
                      headers=headers).status_code == 404


def test_admin_transfer_rejects_unclaimed_roster_entry(account_app) -> None:
    client = account_app.test_client()
    csrf = register(client, account_app, "transfer-unclaimed@example.com")
    event_id = create_event(client, account_app, csrf).json["event"]["id"]
    participant_id = post(client, account_app, csrf, f"/api/events/{event_id}/participants", {
        "name": "Not claimed",
    }).json["participant"]["id"]

    response = post(client, account_app, csrf, f"/api/events/{event_id}/transfer", {"participant_id": participant_id})

    assert response.status_code == 409


@pytest.mark.parametrize("lifecycle_action", ["archive", "cancel"])
def test_admin_transfer_is_blocked_for_read_only_event(account_app, lifecycle_action: str) -> None:
    client = account_app.test_client()
    csrf = register(client, account_app, f"transfer-readonly-{lifecycle_action}@example.com")
    event_id = create_event(client, account_app, csrf).json["event"]["id"]
    headers = {"X-CSRF-Token": csrf, "Origin": account_app.config["APP_ORIGIN"]}
    assert client.post(f"/api/events/{event_id}/{lifecycle_action}", headers=headers).status_code == 200

    response = post(client, account_app, csrf, f"/api/events/{event_id}/transfer", {"participant_id": "missing"})

    assert response.status_code == 409
    assert response.json["code"] == "event_read_only"


@pytest.mark.parametrize("lifecycle_action", ["archive", "cancel"])
def test_revealed_assignment_remains_readable_after_lifecycle_transition(account_app, lifecycle_action: str) -> None:
    admin, admin_csrf, event_id, unused_participant_ids = create_claimed_event(
        account_app, 3, f"retained-reveal-{lifecycle_action}",
    )
    member = account_app.test_client()
    login_csrf = member.get("/api/auth/csrf").json["csrf_token"]
    login = member.post("/api/auth/login", json={
        "email": f"retained-reveal-{lifecycle_action}-0@example.com",
        "password": "correct horse battery staple",
    }, headers={"X-CSRF-Token": login_csrf, "Origin": account_app.config["APP_ORIGIN"]})
    member_csrf = login.json["csrf_token"]
    assert post(admin, account_app, admin_csrf, f"/api/events/{event_id}/drawing", {}).status_code == 200
    revealed = post(member, account_app, member_csrf, f"/api/events/{event_id}/reveal", {})
    assert revealed.status_code == 200

    transition = post(admin, account_app, admin_csrf, f"/api/events/{event_id}/{lifecycle_action}", {})
    repeated = post(member, account_app, member_csrf, f"/api/events/{event_id}/reveal", {})
    unrevealed_member = account_app.test_client()
    login_csrf = unrevealed_member.get("/api/auth/csrf").json["csrf_token"]
    login = unrevealed_member.post("/api/auth/login", json={
        "email": f"retained-reveal-{lifecycle_action}-1@example.com",
        "password": "correct horse battery staple",
    }, headers={"X-CSRF-Token": login_csrf, "Origin": account_app.config["APP_ORIGIN"]})
    blocked_reveal = post(unrevealed_member, account_app, login.json["csrf_token"], f"/api/events/{event_id}/reveal", {})

    assert transition.status_code == 200
    assert repeated.status_code == 200
    assert repeated.json["recipient"] == revealed.json["recipient"]
    assert blocked_reveal.status_code == 409
    assert blocked_reveal.json["code"] == "event_read_only"


def test_account_deletion_anonymizes_roster_without_changing_assignments(account_app) -> None:
    admin = account_app.test_client()
    admin_csrf = register(admin, account_app, "privacy-admin@example.com")
    event_id = create_event(admin, account_app, admin_csrf).json["event"]["id"]
    participant_ids = [post(admin, account_app, admin_csrf, f"/api/events/{event_id}/participants", {
        "name": f"Member {index}",
    }).json["participant"]["id"] for index in range(3)]
    invite_link = post(admin, account_app, admin_csrf, f"/api/events/{event_id}/invite-link", {}).json["link"]
    token = parse_qs(urlsplit(invite_link).fragment)["token"][0]
    clients = []
    for index, participant_id in enumerate(participant_ids):
        client = account_app.test_client()
        csrf = register(client, account_app, f"privacy-member-{index}@example.com")
        assert post(client, account_app, csrf, f"/api/events/{event_id}/claim", {
            "participant_id": participant_id, "token": token,
        }).status_code == 200
        clients.append(client)
    assert post(admin, account_app, admin_csrf, f"/api/events/{event_id}/drawing", {}).status_code == 200
    with Session(account_app.extensions["database"]) as database:
        assignments_before = set(database.execute(select(
            EventAssignment.giver_participant_id, EventAssignment.recipient_participant_id,
        )).all())
        deleted_user_id = database.scalar(select(EventParticipant.user_id).where(
            EventParticipant.id == participant_ids[0],
        ))

    deleting_client = clients[0]
    csrf = deleting_client.get("/api/auth/csrf").json["csrf_token"]
    deleted = deleting_client.delete("/api/auth/account", json={
        "current_password": "correct horse battery staple",
    }, headers={"X-CSRF-Token": csrf, "Origin": account_app.config["APP_ORIGIN"]})

    assert deleted.status_code == 200
    with Session(account_app.extensions["database"]) as database:
        participant = database.get(EventParticipant, participant_ids[0])
        assignments_after = set(database.execute(select(
            EventAssignment.giver_participant_id, EventAssignment.recipient_participant_id,
        )).all())
        assert participant.name == "Deleted user"
        assert participant.user_id is None
        assert database.get(User, deleted_user_id) is None
        assert assignments_after == assignments_before


def test_account_deletion_before_drawing_keeps_anonymized_roster_entry(account_app) -> None:
    admin, unused_admin_csrf, event_id, participant_ids = create_claimed_event(account_app, 3, "pre-draw-delete")
    member = account_app.test_client()
    csrf = member.get("/api/auth/csrf").json["csrf_token"]
    login = member.post("/api/auth/login", json={
        "email": "pre-draw-delete-0@example.com", "password": "correct horse battery staple",
    }, headers={"X-CSRF-Token": csrf, "Origin": account_app.config["APP_ORIGIN"]})
    user_id = login.json["user"]["id"]
    csrf = login.json["csrf_token"]

    deleted = member.delete("/api/auth/account", json={
        "current_password": "correct horse battery staple",
    }, headers={"X-CSRF-Token": csrf, "Origin": account_app.config["APP_ORIGIN"]})

    assert deleted.status_code == 200
    with Session(account_app.extensions["database"]) as database:
        participant = database.get(EventParticipant, participant_ids[0])
        assert participant.name == "Deleted user"
        assert participant.user_id is None
        assert database.get(User, user_id) is None
        assert database.scalar(select(EventAssignment).where(EventAssignment.event_id == event_id)) is None


def test_event_edit_preserves_omitted_values_and_updates_details(account_app) -> None:
    client = account_app.test_client()
    csrf = register(client, account_app, "editor@example.com")
    event_id = create_event(client, account_app, csrf).json["event"]["id"]
    headers = {"X-CSRF-Token": csrf, "Origin": account_app.config["APP_ORIGIN"]}

    response = client.patch(f"/api/events/{event_id}", json={
        "name": "Updated exchange", "location": "Krakow", "currency": "PLN", "budget": "25.25",
    }, headers=headers)

    assert response.status_code == 200
    assert response.json["event"]["name"] == "Updated exchange"
    assert response.json["event"]["exchange_date"] == "2026-12-20"
    assert response.json["event"]["time_zone"] == "Europe/Warsaw"
    assert response.json["event"]["location"] == "Krakow"
    assert response.json["event"]["currency"] == "PLN"
    assert response.json["event"]["budget"] == "25.25"


def test_event_listing_paginates_and_groups_by_event_local_date(account_app) -> None:
    account_app.config["CLOCK"] = lambda: datetime(2026, 12, 19, 23, 30, tzinfo=timezone.utc)
    client = account_app.test_client()
    csrf = register(client, account_app, "planner@example.com")
    event_dates = ("2026-12-19", "2026-12-20", "2026-12-21")
    for index, exchange_date in enumerate(event_dates):
        post(client, account_app, csrf, "/api/events", {
            "name": f"Exchange {index}", "exchange_date": exchange_date, "time_zone": "Europe/Warsaw",
        })

    first_page = client.get("/api/events?page=1&page_size=2").json
    second_page = client.get("/api/events?page=2&page_size=2").json

    assert first_page["total"] == 3
    assert [item["period"] for item in first_page["events"]] == ["past", "ongoing"]
    assert [item["period"] for item in second_page["events"]] == ["upcoming"]


def test_invite_link_exposes_only_roster_availability_before_claim(account_app) -> None:
    admin = account_app.test_client()
    csrf = register(admin, account_app, "invite-admin@example.com")
    event_id = create_event(admin, account_app, csrf).json["event"]["id"]
    added = post(admin, account_app, csrf, f"/api/events/{event_id}/participants", {"name": "Morgan"})
    participant_id = added.json["participant"]["id"]

    generated = post(admin, account_app, csrf, f"/api/events/{event_id}/invite-link", {})
    assert generated.status_code == 200
    token = parse_qs(urlsplit(generated.json["link"]).fragment)["token"][0]
    with Session(account_app.extensions["database"]) as database:
        event = database.get(Event, event_id)
        assert event.invite_token_hash == digest(token)
        assert event.invite_token_encrypted != token

    preview = admin.post(f"/api/events/{event_id}/invitation-preview", json={"token": token})

    assert preview.status_code == 200
    assert preview.json == {"invitation": {
        "event_id": event_id,
        "participants": [{"id": participant_id, "name": "Morgan", "available": True}],
    }}
    assert token not in str(preview.json)
    details = admin.get(f"/api/events/{event_id}")
    assert details.status_code == 200
    assert "invite_token_hash" not in details.json["event"]
    assert "invite_token_encrypted" not in details.json["event"]


def test_claim_grants_membership_and_admin_can_release_a_mistaken_claim(account_app) -> None:
    admin = account_app.test_client()
    admin_csrf = register(admin, account_app, "claim-admin@example.com")
    event_id = create_event(admin, account_app, admin_csrf).json["event"]["id"]
    first = post(admin, account_app, admin_csrf, f"/api/events/{event_id}/participants", {"name": "Morgan"})
    second = post(admin, account_app, admin_csrf, f"/api/events/{event_id}/participants", {"name": "Riley"})
    link = post(admin, account_app, admin_csrf, f"/api/events/{event_id}/invite-link", {}).json["link"]
    token = parse_qs(urlsplit(link).fragment)["token"][0]

    member = account_app.test_client()
    member_csrf = register(member, account_app, "claimant@example.com")
    claimed = post(member, account_app, member_csrf, f"/api/events/{event_id}/claim", {
        "participant_id": first.json["participant"]["id"], "token": token,
    })

    assert claimed.status_code == 200
    assert member.get(f"/api/events/{event_id}").status_code == 200
    assert member.get(f"/api/events/{event_id}/invite-link").json["link"] == link
    denied_email = post(member, account_app, member_csrf, f"/api/events/{event_id}/invitations", {
        "email": "other@example.com",
    })
    assert denied_email.status_code == 403
    duplicate_claim = post(member, account_app, member_csrf, f"/api/events/{event_id}/claim", {
        "participant_id": second.json["participant"]["id"], "token": token,
    })
    assert duplicate_claim.status_code == 409
    assert duplicate_claim.json["code"] == "already_claimed"

    released = member.delete(
        f"/api/events/{event_id}/participants/{first.json['participant']['id']}/claim",
        headers={"X-CSRF-Token": member_csrf, "Origin": account_app.config["APP_ORIGIN"]},
    )
    assert released.status_code == 403
    admin_release = admin.delete(
        f"/api/events/{event_id}/participants/{first.json['participant']['id']}/claim",
        headers={"X-CSRF-Token": admin_csrf, "Origin": account_app.config["APP_ORIGIN"]},
    )
    assert admin_release.status_code == 200
    assert member.get(f"/api/events/{event_id}").status_code == 404


def test_admin_draws_once_and_members_reveal_only_their_own_recipient(account_app) -> None:
    admin = account_app.test_client()
    admin_csrf = register(admin, account_app, "draw-admin@example.com")
    event_id = create_event(admin, account_app, admin_csrf).json["event"]["id"]
    participant_ids = []
    for name in ("Morgan", "Riley", "Taylor"):
        participant_ids.append(post(
            admin, account_app, admin_csrf, f"/api/events/{event_id}/participants", {"name": name},
        ).json["participant"]["id"])
    link = post(admin, account_app, admin_csrf, f"/api/events/{event_id}/invite-link", {}).json["link"]
    token = parse_qs(urlsplit(link).fragment)["token"][0]
    members = []
    for index, participant_id in enumerate(participant_ids):
        member = account_app.test_client()
        member_csrf = register(member, account_app, f"draw-member-{index}@example.com")
        claimed = post(member, account_app, member_csrf, f"/api/events/{event_id}/claim", {
            "participant_id": participant_id, "token": token,
        })
        assert claimed.status_code == 200
        members.append((member, member_csrf, participant_id))

    enabled = post(admin, account_app, admin_csrf, f"/api/events/{event_id}/drawing", {})
    status = admin.get(f"/api/events/{event_id}/drawing")

    assert enabled.status_code == 200
    assert enabled.json["drawing"] == {
        "enabled": True, "participant_count": 3, "revealed_count": 0, "has_revealed": False,
    }
    assert "assignments" not in enabled.json
    assert status.json["drawing"] == {
        "enabled": True, "participant_count": 3, "revealed_count": 0, "has_revealed": False,
    }
    assert "recipient_id" not in str(status.json)
    member_status = members[0][0].get(f"/api/events/{event_id}/drawing")
    assert member_status.json["drawing"]["has_revealed"] is False
    assert member_status.json["drawing"]["revealed_count"] is None
    assert admin.post(f"/api/events/{event_id}/reveal", json={}, headers={
        "X-CSRF-Token": admin_csrf, "Origin": account_app.config["APP_ORIGIN"],
    }).status_code == 404

    revealed = []
    for member, member_csrf, giver_id in members:
        response = post(member, account_app, member_csrf, f"/api/events/{event_id}/reveal", {})
        assert response.status_code == 200
        recipient = response.json["recipient"]
        assert recipient["id"] != giver_id
        revealed.append(recipient["id"])

    assert len(set(revealed)) == len(participant_ids)
    assert set(revealed) == set(participant_ids)
    assert admin.get(f"/api/events/{event_id}/drawing").json["drawing"]["revealed_count"] == 3
    repeated_reveal = post(members[0][0], account_app, members[0][1], f"/api/events/{event_id}/reveal", {})
    reset_after_reveal = admin.delete(f"/api/events/{event_id}/drawing", headers={
        "X-CSRF-Token": admin_csrf, "Origin": account_app.config["APP_ORIGIN"],
    })
    assert repeated_reveal.json["recipient"]["id"] == revealed[0]
    assert reset_after_reveal.status_code == 200
    assert reset_after_reveal.json["drawing"]["enabled"] is False
    with Session(account_app.extensions["database"]) as database:
        event = database.get(Event, event_id)
        assert event.drawing_ever_enabled is False
        assert database.query(EventDraw).filter_by(event_id=event_id).count() == 0
        assert database.query(EventAssignment).filter_by(event_id=event_id).count() == 0


def test_admin_can_reset_after_a_recipient_has_been_revealed(account_app) -> None:
    admin, admin_csrf, event_id, participant_ids = create_claimed_event(account_app, 3, "reset-revealed")
    enabled = admin.post(f"/api/events/{event_id}/drawing", json={}, headers={
        "X-CSRF-Token": admin_csrf, "Origin": account_app.config["APP_ORIGIN"],
    })
    assert enabled.status_code == 200
    with Session(account_app.extensions["database"]) as database:
        assignment = database.query(EventAssignment).filter_by(
            event_id=event_id, giver_participant_id=participant_ids[0],
        ).one()
        assignment.revealed_at = datetime.now(timezone.utc)

    reset = admin.delete(f"/api/events/{event_id}/drawing", headers={
        "X-CSRF-Token": admin_csrf, "Origin": account_app.config["APP_ORIGIN"],
    })

    assert reset.status_code == 200
    assert reset.json["drawing"]["enabled"] is False
    with Session(account_app.extensions["database"]) as database:
        event = database.get(Event, event_id)
        assert event.drawing_ever_enabled is False
        assert database.query(EventDraw).filter_by(event_id=event_id).count() == 0
        assert database.query(EventAssignment).filter_by(event_id=event_id).count() == 0


@pytest.mark.parametrize("participant_count", [3, 4, 8])
def test_draw_rejects_self_pairings_and_is_complete_for_roster_sizes(account_app, participant_count: int) -> None:
    admin, admin_csrf, event_id, participant_ids = create_claimed_event(
        account_app, participant_count, f"draw-size-{participant_count}",
    )
    shuffle_calls = 0

    def controlled_shuffle(recipients):
        nonlocal shuffle_calls
        shuffle_calls += 1
        if shuffle_calls > 1:
            recipients[:] = recipients[1:] + recipients[:1]

    account_app.config["DRAW_SHUFFLE"] = controlled_shuffle
    response = admin.post(f"/api/events/{event_id}/drawing", json={}, headers={
        "X-CSRF-Token": admin_csrf, "Origin": account_app.config["APP_ORIGIN"],
    })

    assert response.status_code == 200
    assert shuffle_calls == 2
    with Session(account_app.extensions["database"]) as database:
        assignments = database.scalars(select(EventAssignment).where(EventAssignment.event_id == event_id)).all()
    givers = [assignment.giver_participant_id for assignment in assignments]
    recipients = [assignment.recipient_participant_id for assignment in assignments]
    assert len(assignments) == participant_count
    assert set(givers) == set(participant_ids)
    assert set(recipients) == set(participant_ids)
    assert all(giver != recipient for giver, recipient in zip(givers, recipients, strict=True))


def test_failed_draw_generation_rolls_back_without_partial_records(account_app) -> None:
    admin, admin_csrf, event_id, unused_participant_ids = create_claimed_event(account_app, 3, "draw-failure")
    account_app.config["DRAW_SHUFFLE"] = lambda recipients: None

    response = admin.post(f"/api/events/{event_id}/drawing", json={}, headers={
        "X-CSRF-Token": admin_csrf, "Origin": account_app.config["APP_ORIGIN"],
    })

    assert response.status_code == 503
    assert response.json["code"] == "draw_generation_failed"
    with Session(account_app.extensions["database"]) as database:
        event = database.get(Event, event_id)
        assert event.drawing_enabled is False
        assert event.drawing_ever_enabled is False
        assert database.query(EventDraw).filter_by(event_id=event_id).count() == 0
        assert database.query(EventAssignment).filter_by(event_id=event_id).count() == 0


def test_reset_erases_drawing_and_restores_setup_state(account_app) -> None:
    admin = account_app.test_client()
    admin_csrf = register(admin, account_app, "draw-reset-admin@example.com")
    event_id = create_event(admin, account_app, admin_csrf).json["event"]["id"]
    participant_ids = []
    for index in range(4):
        response = post(admin, account_app, admin_csrf, f"/api/events/{event_id}/participants", {
            "name": f"Member {index}",
        })
        participant_ids.append(response.json["participant"]["id"])
    link = post(admin, account_app, admin_csrf, f"/api/events/{event_id}/invite-link", {}).json["link"]
    token = parse_qs(urlsplit(link).fragment)["token"][0]
    members = []
    for index, participant_id in enumerate(participant_ids):
        member = account_app.test_client()
        csrf = register(member, account_app, f"draw-reset-member-{index}@example.com")
        if index < 3:
            assert post(member, account_app, csrf, f"/api/events/{event_id}/claim", {
                "participant_id": participant_id, "token": token,
            }).status_code == 200
        members.append((member, csrf))

    headers = {"X-CSRF-Token": admin_csrf, "Origin": account_app.config["APP_ORIGIN"]}
    enabled = admin.post(f"/api/events/{event_id}/drawing", json={}, headers=headers)
    repeated_enable = admin.post(f"/api/events/{event_id}/drawing", json={}, headers=headers)
    assert enabled.status_code == repeated_enable.status_code == 200
    assert enabled.json == repeated_enable.json
    assert enabled.json["drawing"]["participant_count"] == 4
    assert enabled.json["drawing"]["revealed_count"] == 0
    assert post(members[3][0], account_app, members[3][1], f"/api/events/{event_id}/claim", {
        "participant_id": participant_ids[3], "token": token,
    }).status_code == 409
    with Session(account_app.extensions["database"]) as database:
        assignments = database.query(EventAssignment).filter_by(event_id=event_id).all()
        assert len(assignments) == 4
        assert {assignment.giver_participant_id for assignment in assignments} == set(participant_ids)
        assert {assignment.recipient_participant_id for assignment in assignments} == set(participant_ids)

    reset = admin.delete(f"/api/events/{event_id}/drawing", headers=headers)

    assert reset.status_code == 200
    assert reset.json["drawing"]["enabled"] is False
    with Session(account_app.extensions["database"]) as database:
        event = database.get(Event, event_id)
        assert event.drawing_ever_enabled is False
        assert database.query(EventDraw).filter_by(event_id=event_id).count() == 0
        assert database.query(EventAssignment).filter_by(event_id=event_id).count() == 0

    added = post(admin, account_app, admin_csrf, f"/api/events/{event_id}/participants", {"name": "New member"})
    assert added.status_code == 201
    redrawn = admin.post(f"/api/events/{event_id}/drawing", json={}, headers=headers)
    assert redrawn.status_code == 200
    assert redrawn.json["drawing"]["participant_count"] == 5
    with Session(account_app.extensions["database"]) as database:
        assert database.query(EventDraw).filter_by(event_id=event_id).count() == 1
        assert database.query(EventAssignment).filter_by(event_id=event_id).count() == 5


def test_drawing_requires_at_least_three_defined_entries(account_app) -> None:
    admin, admin_csrf, event_id, unused_participant_ids = create_claimed_event(account_app, 2, "draw-too-small")

    response = admin.post(f"/api/events/{event_id}/drawing", json={}, headers={
        "X-CSRF-Token": admin_csrf, "Origin": account_app.config["APP_ORIGIN"],
    })

    assert response.status_code == 409
    assert response.json["code"] == "not_enough_participants"


def test_drawing_can_be_enabled_when_all_entries_are_unclaimed(account_app) -> None:
    admin = account_app.test_client()
    admin_csrf = register(admin, account_app, "all-unclaimed-admin@example.com")
    event_id = create_event(admin, account_app, admin_csrf).json["event"]["id"]
    participant_ids = []
    for index in range(3):
        response = post(admin, account_app, admin_csrf, f"/api/events/{event_id}/participants", {
            "name": f"Unclaimed {index}",
        })
        participant_ids.append(response.json["participant"]["id"])

    enabled = post(admin, account_app, admin_csrf, f"/api/events/{event_id}/drawing", {})

    assert enabled.status_code == 200
    assert enabled.json["drawing"]["participant_count"] == 3
    with Session(account_app.extensions["database"]) as database:
        assignments = database.query(EventAssignment).filter_by(event_id=event_id).all()
    assert len(assignments) == 3
    assert {assignment.giver_participant_id for assignment in assignments} == set(participant_ids)
    assert {assignment.recipient_participant_id for assignment in assignments} == set(participant_ids)


def test_claimed_participant_can_reveal_an_unclaimed_recipient(account_app) -> None:
    admin = account_app.test_client()
    admin_csrf = register(admin, account_app, "unclaimed-recipient-admin@example.com")
    event_id = create_event(admin, account_app, admin_csrf).json["event"]["id"]
    participant_ids = []
    for index in range(3):
        participant = post(admin, account_app, admin_csrf, f"/api/events/{event_id}/participants", {
            "name": f"Member {index}",
        })
        participant_ids.append(participant.json["participant"]["id"])
    link = post(admin, account_app, admin_csrf, f"/api/events/{event_id}/invite-link", {}).json["link"]
    token = parse_qs(urlsplit(link).fragment)["token"][0]
    member = account_app.test_client()
    member_csrf = register(member, account_app, "unclaimed-recipient-member@example.com")
    assert post(member, account_app, member_csrf, f"/api/events/{event_id}/claim", {
        "participant_id": participant_ids[1], "token": token,
    }).status_code == 200

    def assign_member_to_unclaimed_recipient(recipients):
        recipients[:] = [recipients[1], recipients[2], recipients[0]]

    account_app.config["DRAW_SHUFFLE"] = assign_member_to_unclaimed_recipient
    enabled = post(admin, account_app, admin_csrf, f"/api/events/{event_id}/drawing", {})
    revealed = post(member, account_app, member_csrf, f"/api/events/{event_id}/reveal", {})

    assert enabled.status_code == 200
    assert revealed.status_code == 200
    assert revealed.json["recipient"] == {"id": participant_ids[2], "name": "Member 2"}


def test_revoked_invite_link_cannot_be_previewed_or_shared(account_app) -> None:
    admin = account_app.test_client()
    csrf = register(admin, account_app, "revoke-admin@example.com")
    event_id = create_event(admin, account_app, csrf).json["event"]["id"]
    link = post(admin, account_app, csrf, f"/api/events/{event_id}/invite-link", {}).json["link"]
    token = parse_qs(urlsplit(link).fragment)["token"][0]
    revoked = admin.delete(f"/api/events/{event_id}/invite-link", headers={
        "X-CSRF-Token": csrf, "Origin": account_app.config["APP_ORIGIN"],
    })

    preview = admin.post(f"/api/events/{event_id}/invitation-preview", json={"token": token})
    share = admin.get(f"/api/events/{event_id}/invite-link")

    assert revoked.status_code == 200
    assert preview.status_code == 404
    assert share.status_code == 404


def test_regenerating_an_invite_link_invalidates_the_previous_token(account_app) -> None:
    admin = account_app.test_client()
    csrf = register(admin, account_app, "rotate-admin@example.com")
    event_id = create_event(admin, account_app, csrf).json["event"]["id"]
    first_link = post(admin, account_app, csrf, f"/api/events/{event_id}/invite-link", {}).json["link"]
    second_link = post(admin, account_app, csrf, f"/api/events/{event_id}/invite-link", {}).json["link"]
    first_token = parse_qs(urlsplit(first_link).fragment)["token"][0]
    second_token = parse_qs(urlsplit(second_link).fragment)["token"][0]

    stale_preview = admin.post(f"/api/events/{event_id}/invitation-preview", json={"token": first_token})
    active_preview = admin.post(f"/api/events/{event_id}/invitation-preview", json={"token": second_token})

    assert first_token != second_token
    assert stale_preview.status_code == 404
    assert active_preview.status_code == 200


def test_invitation_preview_is_rate_limited(account_app) -> None:
    account_app.config["AUTH_RATE_LIMIT"] = 1
    admin = account_app.test_client()
    csrf = register(admin, account_app, "limited-preview-admin@example.com")
    event_id = create_event(admin, account_app, csrf).json["event"]["id"]
    link = post(admin, account_app, csrf, f"/api/events/{event_id}/invite-link", {}).json["link"]
    token = parse_qs(urlsplit(link).fragment)["token"][0]

    first_preview = admin.post(f"/api/events/{event_id}/invitation-preview", json={"token": token})
    second_preview = admin.post(f"/api/events/{event_id}/invitation-preview", json={"token": token})

    assert first_preview.status_code == 200
    assert second_preview.status_code == 429
    assert second_preview.json["code"] == "rate_limited"


@pytest.mark.parametrize("read_only_state", ["archived", "cancelled", "drawing_enabled"])
def test_claim_is_rejected_when_event_becomes_read_only(account_app, read_only_state: str) -> None:
    admin = account_app.test_client()
    admin_csrf = register(admin, account_app, "readonly-admin@example.com")
    event_id = create_event(admin, account_app, admin_csrf).json["event"]["id"]
    participant = post(admin, account_app, admin_csrf, f"/api/events/{event_id}/participants", {"name": "Morgan"})
    link = post(admin, account_app, admin_csrf, f"/api/events/{event_id}/invite-link", {}).json["link"]
    token = parse_qs(urlsplit(link).fragment)["token"][0]
    with Session(account_app.extensions["database"]) as database, database.begin():
        event = database.get(Event, event_id)
        if read_only_state == "archived":
            event.archived = True
        elif read_only_state == "cancelled":
            event.cancelled = True
        else:
            event.drawing_enabled = True
            event.drawing_ever_enabled = True
    attendee = account_app.test_client()
    attendee_csrf = register(attendee, account_app, "readonly-attendee@example.com")

    claim = post(attendee, account_app, attendee_csrf, f"/api/events/{event_id}/claim", {
        "participant_id": participant.json["participant"]["id"], "token": token,
    })

    assert claim.status_code == 409
    assert claim.json["code"] == "event_read_only"


def test_invitation_email_uses_known_recipient_language_and_active_outbox(account_app) -> None:
    admin = account_app.test_client()
    admin_csrf = register(admin, account_app, "mail-admin@example.com")
    event_id = create_event(admin, account_app, admin_csrf, "Polish exchange").json["event"]["id"]
    recipient = account_app.test_client()
    register(recipient, account_app, "ola@example.com", "Ola", "pl")

    queued = post(admin, account_app, admin_csrf, f"/api/events/{event_id}/invitations", {
        "email": "ola@example.com",
    })
    with Session(account_app.extensions["database"]) as database:
        message = database.query(EmailMessage).one()
        payload = json.loads(Fernet(account_app.config["OUTBOX_KEY"].encode()).decrypt(message.payload.encode()))

    sent = []
    delivered = deliver_pending(account_app, sent.append)

    assert queued.status_code == 202
    assert payload["to"] == "ola@example.com"
    assert payload["subject"] == "Zaproszenie GIVVI: Polish exchange"
    assert "/invite/" in payload["body"]
    assert delivered == 1
    assert sent == [payload]


def test_worker_discards_queued_invitation_after_link_revocation(account_app) -> None:
    admin = account_app.test_client()
    csrf = register(admin, account_app, "stale-mail-admin@example.com")
    event_id = create_event(admin, account_app, csrf).json["event"]["id"]
    queued = post(admin, account_app, csrf, f"/api/events/{event_id}/invitations", {
        "email": "guest@example.com",
    })
    revoked = admin.delete(f"/api/events/{event_id}/invite-link", headers={
        "X-CSRF-Token": csrf, "Origin": account_app.config["APP_ORIGIN"],
    })
    sent = []

    delivered = deliver_pending(account_app, sent.append)

    with Session(account_app.extensions["database"]) as database:
        message = database.scalar(select(EmailMessage))
        assert message.payload is None
        assert message.failed_at is not None
    assert queued.status_code == 202
    assert revoked.status_code == 200
    assert delivered == 0
    assert sent == []


def test_worker_discards_queued_invitation_after_event_is_archived(account_app) -> None:
    admin = account_app.test_client()
    csrf = register(admin, account_app, "archived-mail-admin@example.com")
    event_id = create_event(admin, account_app, csrf).json["event"]["id"]
    post(admin, account_app, csrf, f"/api/events/{event_id}/invitations", {"email": "guest@example.com"})
    with Session(account_app.extensions["database"]) as database, database.begin():
        database.get(Event, event_id).archived = True
    sent = []

    delivered = deliver_pending(account_app, sent.append)

    assert delivered == 0
    assert sent == []


def test_invitation_email_uses_english_when_recipient_language_is_unknown(account_app) -> None:
    admin = account_app.test_client()
    csrf = register(admin, account_app, "fallback-mail-admin@example.com")
    event_id = create_event(admin, account_app, csrf, "Winter exchange").json["event"]["id"]

    queued = post(admin, account_app, csrf, f"/api/events/{event_id}/invitations", {
        "email": "unknown@example.com",
    })

    with Session(account_app.extensions["database"]) as database:
        message = database.scalar(select(EmailMessage))
        payload = json.loads(Fernet(account_app.config["OUTBOX_KEY"].encode()).decrypt(message.payload.encode()))
    assert queued.status_code == 202
    assert payload["subject"] == "GIVVI invitation: Winter exchange"
