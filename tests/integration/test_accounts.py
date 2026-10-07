from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import os
from threading import Barrier
from uuid import uuid4

from alembic import command
from alembic.config import Config
from argon2 import PasswordHasher
from cryptography.fernet import Fernet
import pytest
from sqlalchemy import create_engine
from sqlalchemy import inspect
from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.schema import CreateSchema
from sqlalchemy.schema import DropSchema
from sqlalchemy.orm import Session

from givvi import create_app
from givvi.accounts.security import digest
from givvi.accounts.security import now
from givvi.accounts.services import reset_password
from givvi.errors import ApiError
from givvi.models import AccountToken
from givvi.models import User
from givvi.models import Wishlist


@pytest.fixture
def migrated_app():
    url = os.environ.get("GIVVI_TEST_DATABASE_URL")
    if not url:
        pytest.fail("GIVVI_TEST_DATABASE_URL is required")
    schema = f"test_{uuid4().hex}"
    admin_engine = create_engine(url)
    with admin_engine.begin() as connection:
        connection.execute(CreateSchema(schema))
    scoped_url = make_url(url).update_query_dict({"options": f"-csearch_path={schema}"})
    app = create_app({"TESTING": True, "DATABASE_URL": scoped_url,
                     "OUTBOX_KEY": Fernet.generate_key().decode(), "COOKIE_SECURE": False})
    config = Config("alembic.ini")
    try:
        with app.extensions["database"].begin() as connection:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        yield app, config
    finally:
        app.extensions["database"].dispose()
        with admin_engine.begin() as connection:
            connection.execute(DropSchema(schema, cascade=True))
        admin_engine.dispose()


@pytest.mark.integration
def test_migration_upgrade_downgrade_and_registration(migrated_app) -> None:
    app, config = migrated_app
    client = app.test_client()
    token = client.get("/api/auth/csrf").json["csrf_token"]

    response = client.post("/api/auth/register", json={
        "name": "Alice", "email": "alice@example.com", "password": "correct horse battery staple",
    }, headers={"X-CSRF-Token": token, "Origin": app.config["APP_ORIGIN"]})

    assert response.status_code == 202
    with app.extensions["database"].begin() as connection:
        config.attributes["connection"] = connection
        command.check(config)
        command.downgrade(config, "base")
        assert "users" not in inspect(connection).get_table_names()
        command.upgrade(config, "head")
        assert "users" in inspect(connection).get_table_names()


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

    assert statuses == [202, 202]
    with Session(app.extensions["database"]) as database:
        assert len(database.scalars(select(User)).all()) == 1
        assert len(database.scalars(select(Wishlist)).all()) == 1


@pytest.mark.integration
def test_competing_resets_consume_token_once(migrated_app) -> None:
    app, config = migrated_app
    raw_token = "a-test-only-reset-token"
    with app.app_context(), Session(app.extensions["database"]) as database, database.begin():
        user = User(name="Alice", email="alice@example.com", password_hash=PasswordHasher().hash("original test password"), verified_at=now())
        database.add(user)
        database.flush()
        database.add(Wishlist(user_id=user.id))
        database.add(AccountToken(id=digest(raw_token), user_id=user.id, purpose="reset", expires_at=now() + timedelta(minutes=30)))
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
