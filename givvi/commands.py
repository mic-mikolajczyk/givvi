from threading import Event

from alembic import command
from alembic.config import Config
import click
from flask import Flask
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from givvi.accounts.services import reapply_account_deletions
from givvi.mail import deliver_pending


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
