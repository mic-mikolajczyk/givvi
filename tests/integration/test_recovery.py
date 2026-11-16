from datetime import date
from datetime import timedelta
from io import BytesIO
import os
import subprocess
import sys
import tarfile
from time import perf_counter
from uuid import uuid4

from alembic import command
from alembic.config import Config
from argon2 import PasswordHasher
from cryptography.fernet import Fernet
import pytest
from sqlalchemy import create_engine
from sqlalchemy import select
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from givvi import create_app
from givvi.accounts.security import digest
from givvi.accounts.security import new_session
from givvi.accounts.security import now
from givvi.accounts.services import delete_account
from givvi.events.services import enable_drawing
from givvi.models import AccountToken
from givvi.models import EmailMessage
from givvi.models import Event
from givvi.models import EventAssignment
from givvi.models import EventParticipant
from givvi.models import Gift
from givvi.models import LoginSession
from givvi.models import User
from givvi.models import Wishlist

POSTGRES_CLIENT_IMAGE = "postgres:17.6-bookworm"


@pytest.fixture
def recovery_databases():
    raw_url = os.environ.get("GIVVI_TEST_DATABASE_URL")
    if not raw_url:
        pytest.fail("GIVVI_TEST_DATABASE_URL is required")
    url = make_url(raw_url)
    admin = create_engine(url, isolation_level="AUTOCOMMIT")
    names = [f"recovery_{uuid4().hex}" for unused_index in range(2)]
    applications = []
    key = Fernet.generate_key().decode()
    try:
        for name in names:
            with admin.connect() as connection:
                connection.execute(text(f'CREATE DATABASE "{name}"'))
            applications.append(create_app({
                "TESTING": True, "DATABASE_URL": url.set(database=name), "COOKIE_SECURE": False, "OUTBOX_KEY": key,
            }))
        yield applications
    finally:
        for application in applications:
            application.extensions["database"].dispose()
        with admin.connect() as connection:
            for name in names:
                connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        admin.dispose()


def postgres_client(app, command_name: str, data: bytes | None = None) -> bytes:
    url = make_url(app.config["DATABASE_URL"])
    environment = dict(os.environ, PGHOST=url.host or "127.0.0.1", PGPORT=str(url.port or 5432),
                       PGUSER=url.username or "", PGPASSWORD=url.password or "", PGDATABASE=url.database or "")
    arguments = ["docker", "run", "--rm", "-i", "--network", "host"]
    for name in ("PGHOST", "PGPORT", "PGUSER", "PGPASSWORD", "PGDATABASE"):
        arguments.extend(("--env", name))
    arguments.extend((POSTGRES_CLIENT_IMAGE, command_name, "--no-owner", "--no-acl"))
    arguments.extend(("--format=custom",) if command_name == "pg_dump" else ("--exit-on-error", "--dbname", url.database))
    return subprocess.run(arguments, input=data, capture_output=True, env=environment, check=True).stdout


@pytest.mark.integration
def test_encrypted_restore_replays_deletions_and_previous_api(recovery_databases, tmp_path) -> None:
    source, restored = recovery_databases
    config = Config("alembic.ini")
    with source.extensions["database"].begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")
    password = "synthetic recovery password"
    with source.app_context(), Session(source.extensions["database"]) as database, database.begin():
        users = [User(name=f"Synthetic {index}", email=f"restore-{index}@example.com",
                      password_hash=PasswordHasher().hash(password)) for index in range(3)]
        database.add_all(users)
        database.flush()
        admin_id, deleted_id, other_id = [user.id for user in users]
        database.add_all([Wishlist(user_id=user.id) for user in users])
        database.flush()
        database.add(Gift(wishlist_id=deleted_id, name="Synthetic private gift", position=0))
        event = Event(admin_id=admin_id, name="Synthetic restore", exchange_date=date(2026, 12, 20), time_zone="UTC")
        database.add(event)
        database.flush()
        event_id = event.id
        roster = [EventParticipant(event_id=event_id, user_id=user.id, name=f"Roster {index}")
                  for index, user in enumerate(users)]
        database.add_all(roster)
        cookie, unused_csrf = new_session(database, admin_id)
        new_session(database, deleted_id)
        database.add(AccountToken(
            id=digest("synthetic-reset"),
            user_id=deleted_id,
            purpose="reset",
            expires_at=now() + timedelta(minutes=30),
        ))
        database.add(EmailMessage(
            user_id=deleted_id,
            payload="synthetic-encrypted-payload",
            available_at=now(),
            expires_at=now() + timedelta(minutes=30),
        ))
        database.flush()
        enable_drawing(database, event)
        assignments_before = sorted(database.execute(select(
            EventAssignment.giver_participant_id, EventAssignment.recipient_participant_id,
        )).all())
        deleted_participant_id = roster[1].id

    encryption = Fernet(Fernet.generate_key())
    archive = tmp_path / "snapshot.fernet"
    archive.write_bytes(encryption.encrypt(postgres_client(source, "pg_dump")))
    archive.chmod(0o600)
    with source.app_context(), Session(source.extensions["database"]) as database, database.begin():
        delete_account(database, database.get(User, deleted_id), {"current_password": password})
    ledger = source.test_cli_runner().invoke(args=["export-deletion-ledger"])
    assert ledger.exit_code == 0

    started = perf_counter()
    postgres_client(restored, "pg_restore", encryption.decrypt(archive.read_bytes()))
    with Session(restored.extensions["database"]) as database:
        assert database.get(User, deleted_id) is not None
    sanitized = restored.test_cli_runner().invoke(
        args=["import-deletion-ledger", "--confirm-isolated-restore"], input=ledger.output,
    )
    assert sanitized.exit_code == 0, sanitized.output
    with Session(restored.extensions["database"]) as database:
        for model, column in ((User, User.id), (Wishlist, Wishlist.user_id), (Gift, Gift.wishlist_id),
                              (LoginSession, LoginSession.user_id), (AccountToken, AccountToken.user_id),
                              (EmailMessage, EmailMessage.user_id)):
            assert database.scalar(select(model).where(column == deleted_id)) is None
        participant = database.get(EventParticipant, deleted_participant_id)
        assert participant.name == "Deleted user"
        assert participant.user_id is None
        assert database.get(User, other_id) is not None
        assert sorted(database.execute(select(
            EventAssignment.giver_participant_id, EventAssignment.recipient_participant_id,
        )).all()) == assignments_before

    reference = os.environ.get("GIVVI_ROLLBACK_REF", "HEAD")
    revision = subprocess.run(["git", "rev-parse", reference], capture_output=True, text=True, check=True).stdout.strip()
    previous_code = subprocess.run(["git", "archive", revision, "givvi"], capture_output=True, check=True).stdout
    rollback_directory = tmp_path / "previous-api"
    rollback_directory.mkdir()
    with tarfile.open(fileobj=BytesIO(previous_code)) as archive_file:
        archive_file.extractall(rollback_directory, filter="data")
    environment = dict(os.environ, GIVVI_DATABASE_URL=make_url(restored.config["DATABASE_URL"]).render_as_string(
        hide_password=False), GIVVI_OUTBOX_KEY=source.config["OUTBOX_KEY"], RECOVERY_COOKIE=cookie, RECOVERY_EVENT=event_id)
    environment.pop("PYTHONPATH", None)
    rollback = subprocess.run([sys.executable, "-c", """
import os
from givvi import create_app
app = create_app({"TESTING": True, "COOKIE_SECURE": False})
client = app.test_client()
client.set_cookie("givvi_session", os.environ["RECOVERY_COOKIE"])
assert client.get("/api/health/ready").status_code == 200
assert client.get("/api/events").status_code == 200
assert client.get("/api/events/" + os.environ["RECOVERY_EVENT"]).status_code == 200
print("previous-api-compatible")
"""], cwd=rollback_directory, env=environment, capture_output=True, text=True)
    assert rollback.returncode == 0, "Previous API failed compatibility checks"
    assert "previous-api-compatible" in rollback.stdout
    elapsed = round(perf_counter() - started, 2)
    print(f"GIVVI_RECOVERY_REHEARSAL restore_and_rollback_seconds={elapsed} previous_revision={revision}")
