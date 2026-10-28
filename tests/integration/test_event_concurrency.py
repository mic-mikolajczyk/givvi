from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from urllib.parse import parse_qs
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from givvi.models import Event
from givvi.models import EventAssignment
from givvi.models import EventDraw
from givvi.models import EventParticipant


def register(client, app, email: str) -> str:
    csrf = client.get("/api/auth/csrf").json["csrf_token"]
    response = client.post("/api/auth/register", json={
        "name": "Participant", "email": email, "password": "correct horse battery staple",
    }, headers={"X-CSRF-Token": csrf, "Origin": app.config["APP_ORIGIN"]})
    assert response.status_code == 201
    return response.json["csrf_token"]


def create_invited_event(app, entry_names: tuple[str, ...]):
    admin = app.test_client()
    csrf = register(admin, app, f"admin-{uuid4()}@example.com")
    event_response = admin.post("/api/events", json={
        "name": "Concurrent exchange", "exchange_date": "2026-12-20", "time_zone": "UTC",
    }, headers={"X-CSRF-Token": csrf, "Origin": app.config["APP_ORIGIN"]})
    event_id = event_response.json["event"]["id"]
    participant_ids = []
    for name in entry_names:
        response = admin.post(f"/api/events/{event_id}/participants", json={"name": name}, headers={
            "X-CSRF-Token": csrf, "Origin": app.config["APP_ORIGIN"],
        })
        participant_ids.append(response.json["participant"]["id"])
    link_response = admin.post(f"/api/events/{event_id}/invite-link", json={}, headers={
        "X-CSRF-Token": csrf, "Origin": app.config["APP_ORIGIN"],
    })
    token = parse_qs(urlsplit(link_response.json["link"]).fragment)["token"][0]
    return admin, csrf, event_id, participant_ids, token


@pytest.mark.integration
def test_competing_admin_transfers_are_serialized(migrated_app) -> None:
    app, unused_config = migrated_app
    admin, admin_csrf, event_id, participant_ids, token = create_invited_event(app, ("Morgan", "Riley"))
    for index, participant_id in enumerate(participant_ids):
        member = app.test_client()
        member_csrf = register(member, app, f"transfer-member-{uuid4()}@example.com")
        claimed = member.post(f"/api/events/{event_id}/claim", json={
            "participant_id": participant_id, "token": token,
        }, headers={"X-CSRF-Token": member_csrf, "Origin": app.config["APP_ORIGIN"]})
        assert claimed.status_code == 200

    admin_user = admin.get("/api/auth/me").json["user"]
    second_admin = app.test_client()
    login_csrf = second_admin.get("/api/auth/csrf").json["csrf_token"]
    login = second_admin.post("/api/auth/login", json={
        "email": admin_user["email"], "password": "correct horse battery staple",
    }, headers={"X-CSRF-Token": login_csrf, "Origin": app.config["APP_ORIGIN"]})
    assert login.status_code == 200
    second_admin_csrf = login.json["csrf_token"]
    barrier = Barrier(2)

    def transfer_once(client, csrf: str, participant_id: str) -> int:
        barrier.wait(timeout=10)
        return client.post(f"/api/events/{event_id}/transfer", json={"participant_id": participant_id}, headers={
            "X-CSRF-Token": csrf, "Origin": app.config["APP_ORIGIN"],
        }).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(transfer_once, admin, admin_csrf, participant_ids[0]),
            executor.submit(transfer_once, second_admin, second_admin_csrf, participant_ids[1]),
        ]
        statuses = [future.result() for future in futures]

    assert sorted(statuses) == [200, 404]
    with Session(app.extensions["database"]) as database:
        event = database.get(Event, event_id)
        assert event.admin_id in {
            database.get(EventParticipant, participant_ids[0]).user_id,
            database.get(EventParticipant, participant_ids[1]).user_id,
        }


@pytest.mark.integration
def test_competing_users_cannot_claim_the_same_roster_entry(migrated_app) -> None:
    app, unused_config = migrated_app
    unused_admin, unused_csrf, event_id, participant_ids, token = create_invited_event(app, ("Morgan",))
    clients = [app.test_client(), app.test_client()]
    for client in clients:
        register(client, app, f"claimant-{uuid4()}@example.com")
    barrier = Barrier(2)

    def claim_at_once(client) -> int:
        barrier.wait(timeout=10)
        csrf = client.get("/api/auth/csrf").json["csrf_token"]
        return client.post(f"/api/events/{event_id}/claim", json={
            "participant_id": participant_ids[0], "token": token,
        }, headers={"X-CSRF-Token": csrf, "Origin": app.config["APP_ORIGIN"]}).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses = list(executor.map(claim_at_once, clients))

    assert sorted(statuses) == [200, 409]
    with Session(app.extensions["database"]) as database:
        participant = database.get(EventParticipant, participant_ids[0])
        assert participant.user_id is not None


@pytest.mark.integration
def test_one_account_cannot_claim_two_entries_concurrently(migrated_app) -> None:
    app, unused_config = migrated_app
    unused_admin, unused_csrf, event_id, participant_ids, token = create_invited_event(
        app, ("Morgan", "Riley"),
    )
    email = f"claimant-{uuid4()}@example.com"
    first_client = app.test_client()
    register(first_client, app, email)
    second_client = app.test_client()
    csrf = second_client.get("/api/auth/csrf").json["csrf_token"]
    login = second_client.post("/api/auth/login", json={
        "email": email, "password": "correct horse battery staple",
    }, headers={"X-CSRF-Token": csrf, "Origin": app.config["APP_ORIGIN"]})
    assert login.status_code == 200
    second_csrf = login.json["csrf_token"]
    barrier = Barrier(2)

    def claim_at_once(client, participant_id: str, client_csrf: str) -> int:
        barrier.wait(timeout=10)
        return client.post(f"/api/events/{event_id}/claim", json={
            "participant_id": participant_id, "token": token,
        }, headers={"X-CSRF-Token": client_csrf, "Origin": app.config["APP_ORIGIN"]}).status_code

    first_csrf = first_client.get("/api/auth/csrf").json["csrf_token"]
    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(claim_at_once, first_client, participant_ids[0], first_csrf),
            executor.submit(claim_at_once, second_client, participant_ids[1], second_csrf),
        ]
        statuses = [future.result() for future in futures]

    assert sorted(statuses) == [200, 409]
    with Session(app.extensions["database"]) as database:
        claimed = database.scalars(select(EventParticipant).where(
            EventParticipant.event_id == event_id, EventParticipant.user_id.is_not(None),
        )).all()
        assert len(claimed) == 1


@pytest.mark.integration
def test_claim_and_roster_removal_are_serialized(migrated_app) -> None:
    app, unused_config = migrated_app
    admin, admin_csrf, event_id, participant_ids, token = create_invited_event(app, ("Morgan",))
    member = app.test_client()
    register(member, app, f"claimant-{uuid4()}@example.com")
    member_csrf = member.get("/api/auth/csrf").json["csrf_token"]
    barrier = Barrier(2)

    def claim_once() -> int:
        barrier.wait(timeout=10)
        return member.post(f"/api/events/{event_id}/claim", json={
            "participant_id": participant_ids[0], "token": token,
        }, headers={"X-CSRF-Token": member_csrf, "Origin": app.config["APP_ORIGIN"]}).status_code

    def remove_once() -> int:
        barrier.wait(timeout=10)
        return admin.delete(f"/api/events/{event_id}/participants/{participant_ids[0]}", headers={
            "X-CSRF-Token": admin_csrf, "Origin": app.config["APP_ORIGIN"],
        }).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        claim_future = executor.submit(claim_once)
        remove_future = executor.submit(remove_once)
        claim_status = claim_future.result()
        remove_status = remove_future.result()

    assert (claim_status, remove_status) in ((200, 409), (404, 200))


@pytest.mark.integration
def test_claim_and_draw_generation_are_serialized(migrated_app) -> None:
    app, unused_config = migrated_app
    admin, admin_csrf, event_id, participant_ids, token = create_invited_event(
        app, ("Morgan", "Riley", "Taylor"),
    )
    members = []
    for index, participant_id in enumerate(participant_ids):
        client = app.test_client()
        csrf = register(client, app, f"draw-race-member-{uuid4()}@example.com")
        members.append((client, csrf))
        if index < 2:
            response = client.post(f"/api/events/{event_id}/claim", json={
                "participant_id": participant_id, "token": token,
            }, headers={"X-CSRF-Token": csrf, "Origin": app.config["APP_ORIGIN"]})
            assert response.status_code == 200
    barrier = Barrier(2)

    def enable_drawing() -> int:
        barrier.wait(timeout=10)
        return admin.post(f"/api/events/{event_id}/drawing", json={}, headers={
            "X-CSRF-Token": admin_csrf, "Origin": app.config["APP_ORIGIN"],
        }).status_code

    def claim_last_entry() -> int:
        barrier.wait(timeout=10)
        client, csrf = members[2]
        return client.post(f"/api/events/{event_id}/claim", json={
            "participant_id": participant_ids[2], "token": token,
        }, headers={"X-CSRF-Token": csrf, "Origin": app.config["APP_ORIGIN"]}).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        draw_future = executor.submit(enable_drawing)
        claim_future = executor.submit(claim_last_entry)
        draw_status = draw_future.result()
        claim_status = claim_future.result()

    assert draw_status == 200
    assert claim_status in (200, 409)
    with Session(app.extensions["database"]) as database:
        event = database.get(Event, event_id)
        assignments = database.scalars(select(EventAssignment).where(EventAssignment.event_id == event_id)).all()
        assert event.drawing_enabled is True
        assert {assignment.giver_participant_id for assignment in assignments} == set(participant_ids)
        assert {assignment.recipient_participant_id for assignment in assignments} == set(participant_ids)


def create_claimed_draw(app):
    admin, admin_csrf, event_id, participant_ids, token = create_invited_event(
        app, ("Morgan", "Riley", "Taylor"),
    )
    members = []
    for index, participant_id in enumerate(participant_ids):
        client = app.test_client()
        csrf = register(client, app, f"revealer-{uuid4()}@example.com")
        claimed = client.post(f"/api/events/{event_id}/claim", json={
            "participant_id": participant_id, "token": token,
        }, headers={"X-CSRF-Token": csrf, "Origin": app.config["APP_ORIGIN"]})
        assert claimed.status_code == 200
        members.append((client, csrf))
    enabled = admin.post(f"/api/events/{event_id}/drawing", json={}, headers={
        "X-CSRF-Token": admin_csrf, "Origin": app.config["APP_ORIGIN"],
    })
    assert enabled.status_code == 200
    return admin, admin_csrf, event_id, members


@pytest.mark.integration
def test_reveal_and_reset_are_serialized(migrated_app) -> None:
    app, unused_config = migrated_app
    admin, admin_csrf, event_id, members = create_claimed_draw(app)
    barrier = Barrier(2)

    def reveal_once() -> int:
        barrier.wait(timeout=10)
        client, csrf = members[0]
        return client.post(f"/api/events/{event_id}/reveal", json={}, headers={
            "X-CSRF-Token": csrf, "Origin": app.config["APP_ORIGIN"],
        }).status_code

    def reset_once() -> int:
        barrier.wait(timeout=10)
        return admin.delete(f"/api/events/{event_id}/drawing", headers={
            "X-CSRF-Token": admin_csrf, "Origin": app.config["APP_ORIGIN"],
        }).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        reveal_future = executor.submit(reveal_once)
        reset_future = executor.submit(reset_once)
        reveal_status = reveal_future.result()
        reset_status = reset_future.result()

    assert (reveal_status, reset_status) in ((200, 200), (409, 200))
    with Session(app.extensions["database"]) as database:
        event = database.get(Event, event_id)
        assert event.drawing_enabled is False
        assert event.drawing_ever_enabled is False
        assert database.query(EventDraw).filter_by(event_id=event_id).count() == 0
        assert database.query(EventAssignment).filter_by(event_id=event_id).count() == 0


@pytest.mark.integration
def test_reveal_and_cancel_transition_are_serialized(migrated_app) -> None:
    app, unused_config = migrated_app
    admin, unused_admin_csrf, event_id, members = create_claimed_draw(app)
    barrier = Barrier(2)

    def reveal_once() -> int:
        barrier.wait(timeout=10)
        client, csrf = members[0]
        return client.post(f"/api/events/{event_id}/reveal", json={}, headers={
            "X-CSRF-Token": csrf, "Origin": app.config["APP_ORIGIN"],
        }).status_code

    def cancel_transition() -> None:
        barrier.wait(timeout=10)
        with Session(app.extensions["database"]) as database, database.begin():
            event = database.scalar(select(Event).where(Event.id == event_id).with_for_update())
            event.cancelled = True

    with ThreadPoolExecutor(max_workers=2) as executor:
        reveal_future = executor.submit(reveal_once)
        cancel_future = executor.submit(cancel_transition)
        reveal_status = reveal_future.result()
        cancel_future.result()

    assert reveal_status in (200, 409)
    with Session(app.extensions["database"]) as database:
        event = database.get(Event, event_id)
        assert event.cancelled is True
    if reveal_status == 200:
        client, csrf = members[0]
        repeated_reveal = client.post(f"/api/events/{event_id}/reveal", json={}, headers={
            "X-CSRF-Token": csrf, "Origin": app.config["APP_ORIGIN"],
        })
        assert repeated_reveal.status_code == 200
    else:
        assert reveal_status == 409


@pytest.mark.integration
def test_roster_addition_and_draw_generation_are_serialized(migrated_app) -> None:
    app, unused_config = migrated_app
    admin, admin_csrf, event_id, participant_ids, token = create_invited_event(
        app, ("Morgan", "Riley", "Taylor"),
    )
    for index, participant_id in enumerate(participant_ids):
        client = app.test_client()
        csrf = register(client, app, f"roster-draw-member-{uuid4()}@example.com")
        claimed = client.post(f"/api/events/{event_id}/claim", json={
            "participant_id": participant_id, "token": token,
        }, headers={"X-CSRF-Token": csrf, "Origin": app.config["APP_ORIGIN"]})
        assert claimed.status_code == 200
    barrier = Barrier(2)

    def enable_drawing() -> int:
        barrier.wait(timeout=10)
        return admin.post(f"/api/events/{event_id}/drawing", json={}, headers={
            "X-CSRF-Token": admin_csrf, "Origin": app.config["APP_ORIGIN"],
        }).status_code

    def add_roster_entry() -> tuple[int, str | None]:
        barrier.wait(timeout=10)
        response = admin.post(f"/api/events/{event_id}/participants", json={"name": "New entry"}, headers={
            "X-CSRF-Token": admin_csrf, "Origin": app.config["APP_ORIGIN"],
        })
        participant_id = response.json.get("participant", {}).get("id")
        return response.status_code, participant_id

    with ThreadPoolExecutor(max_workers=2) as executor:
        draw_future = executor.submit(enable_drawing)
        add_future = executor.submit(add_roster_entry)
        draw_status = draw_future.result()
        add_status, added_participant_id = add_future.result()

    assert draw_status == 200
    assert add_status in (201, 409)
    with Session(app.extensions["database"]) as database:
        event = database.get(Event, event_id)
        participants = set(database.scalars(select(EventParticipant.id).where(EventParticipant.event_id == event_id)))
        assignments = database.scalars(select(EventAssignment).where(EventAssignment.event_id == event_id)).all()
        assert event.drawing_enabled is True
        assert {assignment.giver_participant_id for assignment in assignments} == participants
        assert {assignment.recipient_participant_id for assignment in assignments} == participants
        if add_status == 201:
            assert added_participant_id in participants


@pytest.mark.integration
def test_postgresql_rejects_self_and_duplicate_recipients(migrated_app) -> None:
    app, unused_config = migrated_app
    unused_admin, unused_csrf, event_id, unused_members = create_claimed_draw(app)
    with Session(app.extensions["database"]) as database:
        assignments = list(database.scalars(select(EventAssignment).where(EventAssignment.event_id == event_id)))
        assert len(assignments) == 3
        first, second = assignments[:2]

        with pytest.raises(IntegrityError):
            database.execute(update(EventAssignment).where(
                EventAssignment.draw_id == first.draw_id,
                EventAssignment.giver_participant_id == first.giver_participant_id,
            ).values(recipient_participant_id=first.giver_participant_id))
        database.rollback()

        with pytest.raises(IntegrityError):
            database.execute(update(EventAssignment).where(
                EventAssignment.draw_id == first.draw_id,
                EventAssignment.giver_participant_id == first.giver_participant_id,
            ).values(recipient_participant_id=second.recipient_participant_id))
        database.rollback()
