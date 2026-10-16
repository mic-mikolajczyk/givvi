from datetime import date
from datetime import datetime
from datetime import timezone

import pytest
from sqlalchemy.orm import Session

from givvi.accounts.security import COOKIE_NAME
from givvi.models import Event


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


def test_event_edit_and_roster_mutation_reject_read_only_state(account_app) -> None:
    client = account_app.test_client()
    csrf = register(client, account_app, "owner@example.com")
    event_id = create_event(client, account_app, csrf).json["event"]["id"]
    with Session(account_app.extensions["database"]) as database, database.begin():
        database.get(Event, event_id).archived = True

    headers = {"X-CSRF-Token": csrf, "Origin": account_app.config["APP_ORIGIN"]}
    event_update = client.patch(f"/api/events/{event_id}", json={"name": "Changed"}, headers=headers)
    roster_add = client.post(f"/api/events/{event_id}/participants", json={"name": "Morgan"}, headers=headers)

    assert event_update.status_code == 409
    assert roster_add.status_code == 409


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
