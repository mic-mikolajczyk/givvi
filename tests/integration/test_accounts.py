from concurrent.futures import ThreadPoolExecutor
from datetime import date
from datetime import timedelta
from threading import Barrier

from alembic import command
from argon2 import PasswordHasher
import pytest
from sqlalchemy import inspect
from sqlalchemy import select
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from givvi.accounts.security import digest
from givvi.accounts.security import now
from givvi.accounts.services import reset_password
from givvi.errors import ApiError
from givvi.models import AccountToken
from givvi.models import Event
from givvi.models import EventParticipant
from givvi.models import User
from givvi.models import Wishlist


@pytest.mark.integration
def test_migration_upgrade_downgrade_and_registration(migrated_app) -> None:
    app, config = migrated_app
    client = app.test_client()
    token = client.get("/api/auth/csrf").json["csrf_token"]

    response = client.post("/api/auth/register", json={
        "name": "Alice", "email": "alice@example.com", "password": "correct horse battery staple",
    }, headers={"X-CSRF-Token": token, "Origin": app.config["APP_ORIGIN"]})

    assert response.status_code == 201
    assert client.get("/api/auth/me").status_code == 200
    with app.extensions["database"].begin() as connection:
        config.attributes["connection"] = connection
        command.check(config)
        command.downgrade(config, "base")
        assert "users" not in inspect(connection).get_table_names()
        assert "events" not in inspect(connection).get_table_names()
        command.upgrade(config, "head")
        assert "users" in inspect(connection).get_table_names()
        assert "events" in inspect(connection).get_table_names()
        assert "event_participants" in inspect(connection).get_table_names()
        assert "gifts" in inspect(connection).get_table_names()
        assert "order_version" in {column["name"] for column in inspect(connection).get_columns("wishlists")}
        assert {"invite_token_hash", "invite_token_encrypted"} <= {
            column["name"] for column in inspect(connection).get_columns("events")
        }


@pytest.mark.integration
def test_database_rejects_duplicate_user_claims_in_one_event(migrated_app) -> None:
    app, unused_config = migrated_app
    with Session(app.extensions["database"]) as database, database.begin():
        admin = User(name="Admin", email="admin@example.com", password_hash="unused", language="en")
        participant = User(name="Participant", email="participant@example.com", password_hash="unused", language="en")
        database.add_all([admin, participant])
        database.flush()
        event = Event(admin_id=admin.id, name="Exchange", exchange_date=date(2026, 12, 20), time_zone="UTC", currency="EUR")
        database.add(event)
        database.flush()
        database.add(EventParticipant(event_id=event.id, name="Roster name", user_id=participant.id))
        database.flush()
        event_id = event.id
        participant_id = participant.id

    with pytest.raises(IntegrityError):
        with Session(app.extensions["database"]) as database, database.begin():
            database.add(EventParticipant(event_id=event_id, name="Second name", user_id=participant_id))
            database.flush()


@pytest.mark.integration
def test_competing_registrations_create_only_one_account(migrated_app) -> None:
    app, config = migrated_app
    barrier = Barrier(2)

    def register_once(unused_index: int) -> int:
        client = app.test_client()
        token = client.get("/api/auth/csrf").json["csrf_token"]
        barrier.wait(timeout=10)
        return client.post("/api/auth/register", json={
            "name": "Alice", "email": "alice@example.com", "password": "correct horse battery staple",
        }, headers={"X-CSRF-Token": token, "Origin": app.config["APP_ORIGIN"]}).status_code

    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses = list(executor.map(register_once, range(2)))

    assert sorted(statuses) == [201, 409]
    with Session(app.extensions["database"]) as database:
        assert len(database.scalars(select(User)).all()) == 1
        assert len(database.scalars(select(Wishlist)).all()) == 1


@pytest.mark.integration
def test_competing_resets_consume_token_once(migrated_app) -> None:
    app, config = migrated_app
    raw_token = "a-test-only-reset-token"
    with app.app_context(), Session(app.extensions["database"]) as database, database.begin():
        user = User(name="Alice", email="alice@example.com", password_hash=PasswordHasher().hash("original test password"))
        database.add(user)
        database.flush()
        database.add(Wishlist(user_id=user.id))
        database.add(AccountToken(id=digest(raw_token), user_id=user.id,
                     purpose="reset", expires_at=now() + timedelta(minutes=30)))
    barrier = Barrier(2)

    def reset_once(unused_index: int) -> int:
        with app.app_context():
            try:
                with Session(app.extensions["database"]) as database, database.begin():
                    barrier.wait(timeout=10)
                    reset_password(database, {"token": raw_token, "password": "new secure test password"})
                return 200
            except ApiError as error:
                return error.status

    with ThreadPoolExecutor(max_workers=2) as executor:
        statuses = list(executor.map(reset_once, range(2)))

    assert sorted(statuses) == [200, 400]


@pytest.mark.integration
def test_upgrade_preserves_unverified_account_and_removes_signup_token(migrated_app) -> None:
    app, config = migrated_app
    password = "existing account password"
    with app.app_context(), app.extensions["database"].begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "0001_accounts")
        connection.execute(User.__table__.insert().values(
            id="legacy-user", name="Alice", email="legacy@example.com",
            password_hash=PasswordHasher().hash(password), language="en",
        ))
        connection.execute(text("INSERT INTO wishlists (user_id) VALUES (:user_id)"), {"user_id": "legacy-user"})
        connection.execute(AccountToken.__table__.insert().values(
            id=digest("legacy-signup-token"), user_id="legacy-user", purpose="verify",
            expires_at=now() + timedelta(hours=24),
        ))

        command.upgrade(config, "head")

        assert "verified_at" not in [column["name"] for column in inspect(connection).get_columns("users")]
        assert connection.execute(select(AccountToken)).all() == []
    client = app.test_client()
    csrf = client.get("/api/auth/csrf").json["csrf_token"]
    response = client.post("/api/auth/login", json={"email": "legacy@example.com", "password": password},
                           headers={"X-CSRF-Token": csrf, "Origin": app.config["APP_ORIGIN"]})
    assert response.status_code == 200
    assert client.get("/api/auth/me").json["user"]["id"] == "legacy-user"
