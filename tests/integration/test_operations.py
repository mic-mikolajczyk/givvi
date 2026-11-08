from concurrent.futures import ThreadPoolExecutor
from datetime import date
from datetime import timedelta
import json
from math import ceil
from threading import Event as ThreadEvent
from time import perf_counter
from unittest.mock import Mock

from cryptography.fernet import Fernet
import pytest
from sqlalchemy import select
from sqlalchemy import text
from sqlalchemy.orm import Session

from givvi.accounts.security import COOKIE_NAME
from givvi.accounts.security import new_session
from givvi.accounts.security import now
from givvi.events.services import rotate_invite_token
from givvi.mail import deliver_pending
from givvi.mail import MAX_DELIVERY_ATTEMPTS
from givvi.models import EmailMessage
from givvi.models import Event
from givvi.models import EventParticipant
from givvi.models import Gift
from givvi.models import User
from givvi.models import Wishlist


@pytest.mark.integration
def test_database_timeouts_are_set_for_each_transaction(migrated_app) -> None:
    app, unused_config = migrated_app

    with app.extensions["database"].connect() as connection:
        assert connection.scalar(text("SHOW statement_timeout")) == "10s"
        assert connection.scalar(text("SHOW lock_timeout")) == "3s"


GROUP_SIZE = 12
LOAD_WORKERS = 4
READS_PER_MEMBER = 8


def queue_test_message(app, attempts: int = 0, expired_lease: bool = False) -> str:
    with app.app_context(), Session(app.extensions["database"]) as database, database.begin():
        payload = {"to": "synthetic@example.com", "subject": "Synthetic", "body": "https://givvi.invalid/notice"}
        message = EmailMessage(
            payload=Fernet(app.config["OUTBOX_KEY"].encode()).encrypt(json.dumps(payload).encode()).decode(),
            available_at=now(), expires_at=now() + timedelta(days=1), attempts=attempts,
            lease_id="expired-worker" if expired_lease else None,
            lease_until=now() - timedelta(seconds=1) if expired_lease else None,
        )
        database.add(message)
        database.flush()
        return message.id


@pytest.mark.integration
def test_workers_do_not_deliver_a_live_lease_twice(migrated_app) -> None:
    app, unused_config = migrated_app
    identifier = queue_test_message(app)
    entered = ThreadEvent()
    release = ThreadEvent()

    def sender(payload: dict) -> None:
        entered.set()
        assert release.wait(timeout=10)

    other_sender = Mock()
    with ThreadPoolExecutor(max_workers=2) as executor:
        first = executor.submit(deliver_pending, app, sender, 1)
        try:
            assert entered.wait(timeout=10)
            second = executor.submit(deliver_pending, app, other_sender, 1)
            assert second.result(timeout=10) == 0
        finally:
            release.set()
        assert first.result(timeout=10) == 1

    other_sender.assert_not_called()
    with Session(app.extensions["database"]) as database:
        message = database.get(EmailMessage, identifier)
        assert message.attempts == 1
        assert message.payload is None
        assert message.delivered_at is not None


@pytest.mark.integration
@pytest.mark.parametrize("attempts", [1, MAX_DELIVERY_ATTEMPTS])
def test_worker_restart_recovers_only_unexhausted_leases(migrated_app, attempts: int) -> None:
    app, unused_config = migrated_app
    identifier = queue_test_message(app, attempts, expired_lease=True)
    sender = Mock()

    delivered = deliver_pending(app, sender)

    assert delivered == int(attempts < MAX_DELIVERY_ATTEMPTS)
    assert sender.call_count == delivered
    with Session(app.extensions["database"]) as database:
        message = database.get(EmailMessage, identifier)
        assert message.payload is None
        assert message.lease_id is None
        assert bool(message.failed_at) == (attempts == MAX_DELIVERY_ATTEMPTS)


@pytest.mark.integration
def test_small_group_load_baseline(migrated_app) -> None:
    app, unused_config = migrated_app
    clients = []
    headers = []
    with app.app_context(), Session(app.extensions["database"]) as database, database.begin():
        users = [User(name=f"Synthetic {index}", email=f"load-{index}@example.com", password_hash="unused")
                 for index in range(GROUP_SIZE + 1)]
        database.add_all(users)
        database.flush()
        event = Event(admin_id=users[0].id, name="Synthetic exchange", exchange_date=date(2026, 12, 20), time_zone="UTC")
        database.add(event)
        database.flush()
        event_id = event.id
        token = rotate_invite_token(event)
        roster = [EventParticipant(event_id=event_id, name=f"Roster {index}") for index in range(GROUP_SIZE)]
        database.add_all(roster)
        for user in users:
            database.add(Wishlist(user_id=user.id))
            database.flush()
            cookie, csrf = new_session(database, user.id)
            client = app.test_client()
            client.set_cookie(COOKIE_NAME, cookie)
            clients.append(client)
            headers.append({"X-CSRF-Token": csrf, "Origin": app.config["APP_ORIGIN"]})
            for position in range(20):
                database.add(Gift(wishlist_id=user.id, name=f"Synthetic gift {position}", position=position))
        database.flush()
        participant_ids = [participant.id for participant in roster]
        member_id = users[1].id

    def timed_request(index: int, operation: str) -> tuple[float, int, int]:
        client = clients[index + 1]
        started = perf_counter()
        if operation == "claim":
            response = client.post(f"/api/events/{event_id}/claim", json={
                "participant_id": participant_ids[index], "token": token,
            }, headers=headers[index + 1])
        elif operation == "reveal":
            response = client.post(f"/api/events/{event_id}/reveal", json={}, headers=headers[index + 1])
        else:
            paths = ["/api/events", f"/api/events/{event_id}", f"/api/events/{event_id}/drawing",
                     f"/api/events/{event_id}/participants/{participant_ids[0]}/wishlist"]
            response = client.get(paths[int(operation) % len(paths)])
        return (perf_counter() - started) * 1000, response.status_code, len(response.data)

    samples = {}
    with ThreadPoolExecutor(max_workers=LOAD_WORKERS) as executor:
        samples["claim"] = list(executor.map(lambda index: timed_request(index, "claim"), range(GROUP_SIZE)))
        enabled = clients[0].post(f"/api/events/{event_id}/drawing", json={}, headers=headers[0])
        assert enabled.status_code == 200
        samples["reveal"] = list(executor.map(lambda index: timed_request(index, "reveal"), range(GROUP_SIZE)))
        samples["read"] = list(executor.map(
            lambda index: timed_request(index % GROUP_SIZE, str(index)), range(GROUP_SIZE * READS_PER_MEMBER),
        ))

    report = {"group_size": GROUP_SIZE, "workers": LOAD_WORKERS, "operations": {}}
    for operation, results in samples.items():
        latencies = sorted(result[0] for result in results)
        failures = sum(status != 200 for unused_latency, status, unused_size in results)
        assert failures == 0
        report["operations"][operation] = {
            "requests": len(results), "errors": failures,
            "p95_ms": round(latencies[ceil(len(latencies) * 0.95) - 1], 2),
            "max_payload_bytes": max(size for unused_latency, unused_status, size in results),
        }
    with Session(app.extensions["database"]) as database:
        plan = database.scalar(text(
            "EXPLAIN (FORMAT JSON) SELECT id FROM event_participants WHERE event_id = :event_id AND user_id = :user_id"
        ), {"event_id": event_id, "user_id": member_id})
        report["membership_plan"] = plan[0]["Plan"]["Node Type"]
        assert len(database.scalars(select(EventParticipant).where(
            EventParticipant.event_id == event_id, EventParticipant.user_id.is_not(None),
        )).all()) == GROUP_SIZE
    print(f"GIVVI_LOAD_BASELINE {json.dumps(report, sort_keys=True)}")
