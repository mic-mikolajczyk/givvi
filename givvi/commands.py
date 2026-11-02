import csv
from datetime import datetime
import sys
from threading import Event
from typing import TextIO
from uuid import UUID

from alembic import command
from alembic.config import Config
import click
from flask import Flask
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from givvi.accounts.security import utc
from givvi.accounts.services import reapply_account_deletions
from givvi.mail import deliver_pending
from givvi.models import AccountDeletionRecord


def register_commands(app: Flask) -> None:
    @app.cli.command("db-upgrade")
    def db_upgrade() -> None:
        with app.extensions["database"].begin() as connection:
            config = Config("alembic.ini")
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        click.echo("Database migration complete")

    @app.cli.command("reapply-account-deletions")
    def restore_account_deletions() -> None:
        with Session(app.extensions["database"]) as database, database.begin():
            count = reapply_account_deletions(database)
        click.echo(f"Reapplied {count} account deletion records")

    @app.cli.command("export-deletion-ledger")
    def export_deletion_ledger() -> None:
        writer = csv.writer(sys.stdout)
        writer.writerow(("user_id", "deleted_at"))
        with Session(app.extensions["database"]) as database:
            for record in database.scalars(select(AccountDeletionRecord).order_by(AccountDeletionRecord.user_id)):
                writer.writerow((record.user_id, utc(record.deleted_at).isoformat()))

    @app.cli.command("import-deletion-ledger")
    @click.option(
        "--confirm-isolated-restore", is_flag=True, help="Confirm the configured database is an offline restore target.",
    )
    @click.argument("ledger", type=click.File("r"), default="-")
    def import_deletion_ledger(confirm_isolated_restore: bool, ledger: TextIO) -> None:
        if not confirm_isolated_restore:
            raise click.UsageError("Pass --confirm-isolated-restore only for an offline restore target")
        reader = csv.DictReader(ledger)
        if reader.fieldnames != ["user_id", "deleted_at"]:
            raise click.ClickException("Invalid deletion ledger")
        engine = app.extensions["database"]
        insert = postgres_insert if engine.dialect.name == "postgresql" else sqlite_insert
        try:
            with Session(engine) as database, database.begin():
                for row in reader:
                    identifier = str(UUID(row["user_id"]))
                    deleted_at = datetime.fromisoformat(row["deleted_at"])
                    if deleted_at.tzinfo is None or len(row) != 2:
                        raise ValueError
                    database.execute(insert(AccountDeletionRecord).values(
                        user_id=identifier, deleted_at=deleted_at,
                    ).on_conflict_do_nothing(index_elements=[AccountDeletionRecord.user_id]))
                count = reapply_account_deletions(database)
        except (ValueError, TypeError, KeyError, csv.Error):
            raise click.ClickException("Invalid deletion ledger") from None
        click.echo(f"Reapplied {count} account deletion records")

    @app.cli.command("mail-worker")
    @click.option("--watch", is_flag=True, help="Continue processing until interrupted.")
    def mail_worker(watch: bool) -> None:
        stop = Event()
        while True:
            try:
                delivered = deliver_pending(app)
                if not watch:
                    click.echo(f"Delivered {delivered} messages")
            except SQLAlchemyError:
                app.logger.error("Email worker database unavailable")
                if not watch:
                    raise click.ClickException("Database unavailable")
            if not watch:
                break
            stop.wait(3)
