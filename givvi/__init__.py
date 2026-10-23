from datetime import datetime
from datetime import timezone
import secrets

from argon2 import PasswordHasher
from cryptography.fernet import Fernet
from flask import Flask
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

from givvi.accounts.controller import accounts
from givvi.commands import register_commands
from givvi.errors import configure_errors
from givvi.events.controller import events
from givvi.health import health
from givvi.wishlists.controller import wishlists

DATABASE_CONNECT_TIMEOUT_SECONDS = 3


def create_app(config: dict[str, object] | None = None) -> Flask:
    """Build an independently configured application instance."""
    app = Flask(__name__)
    app.config.from_mapping(
        DEBUG=False,
        COOKIE_SECURE=True,
        APP_ORIGIN="http://127.0.0.1:5173",
        AUTH_RATE_LIMIT=60,
        SMTP_HOST="127.0.0.1",
        SMTP_PORT=1025,
        SMTP_FROM="noreply@givvi.local",
        SMTP_TLS=False,
        MAX_CONTENT_LENGTH=16384,
        CLOCK=lambda: datetime.now(timezone.utc)
    )
    app.config.from_prefixed_env(prefix="GIVVI")
    if config is not None:
        app.config.update(config)

    database_url = app.config.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("GIVVI_DATABASE_URL must be configured")
    if not app.config.get("OUTBOX_KEY"):
        if not app.testing:
            raise RuntimeError("GIVVI_OUTBOX_KEY must be configured")
        app.config["OUTBOX_KEY"] = Fernet.generate_key().decode()
    Fernet(app.config["OUTBOX_KEY"].encode())
    app.extensions["dummy_password_hash"] = PasswordHasher().hash(secrets.token_urlsafe(32))

    connection_options = {}
    if make_url(database_url).get_backend_name() == "postgresql":
        connection_options["connect_timeout"] = DATABASE_CONNECT_TIMEOUT_SECONDS

    app.extensions["database"] = create_engine(
        database_url,
        pool_pre_ping=True,
        hide_parameters=True,
        connect_args=connection_options
    )
    app.register_blueprint(health)
    configure_errors(app)
    app.register_blueprint(accounts)
    app.register_blueprint(events)
    app.register_blueprint(wishlists)
    register_commands(app)
    return app
