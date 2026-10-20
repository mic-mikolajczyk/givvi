from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from urllib.parse import parse_qs
from urllib.parse import urlsplit
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

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
