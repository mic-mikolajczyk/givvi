from datetime import datetime
from datetime import timezone
import os
from pathlib import Path
import secrets
from urllib.parse import urlsplit

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


def validate_production_config(app: Flask) -> None:
    if app.config["ENVIRONMENT"] != "production":
        return
    origin = urlsplit(app.config["APP_ORIGIN"])
    database = make_url(app.config["DATABASE_URL"])
    unsafe = any((
        app.debug, app.testing, not app.config["COOKIE_SECURE"],
        os.environ.get("FLASK_DEBUG", "0").casefold() not in ("0", "false", ""),
        origin.scheme != "https", not origin.hostname, origin.username, origin.password,
        origin.path not in ("", "/"), origin.query, origin.fragment,
        database.get_backend_name() != "postgresql", database.query.get("sslmode") != "verify-full",
        not app.config["SMTP_TLS"], len(app.config.get("METRICS_TOKEN", "")) < 32,
        app.config.get("OUTBOX_KEY") == "MDEyMzQ1Njc4OTAxMjM0NTY3ODkwMTIzNDU2Nzg5MDE=",
    ))
    if unsafe:
        raise RuntimeError(
            "Production requires HTTPS, secure cookies, verified database TLS, SMTP TLS, private keys, and no debug"
        )


def create_app(config: dict[str, object] | None = None) -> Flask:
    """Build an independently configured application instance."""
    app = Flask(__name__)
    app.config.from_mapping(
        DEBUG=False,
        ENVIRONMENT="development",
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
    for name in ("DATABASE_URL", "OUTBOX_KEY", "METRICS_TOKEN", "SMTP_USERNAME", "SMTP_PASSWORD"):
        if app.config.get(f"{name}_FILE"):
            app.config[name] = Path(app.config[f"{name}_FILE"]).read_text().strip()

    database_url = app.config.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("GIVVI_DATABASE_URL must be configured")
    validate_production_config(app)
    if app.config["ENVIRONMENT"] == "production":
        app.logger.setLevel("INFO")
    if not app.config.get("OUTBOX_KEY"):
        if not app.testing:
            raise RuntimeError("GIVVI_OUTBOX_KEY must be configured")
        app.config["OUTBOX_KEY"] = Fernet.generate_key().decode()
    Fernet(app.config["OUTBOX_KEY"].encode())
    app.extensions["dummy_password_hash"] = PasswordHasher().hash(secrets.token_urlsafe(32))

    connection_options = {}
    pool_options = {}
    database = make_url(database_url)
    if database.get_backend_name() == "postgresql":
        connection_options["connect_timeout"] = DATABASE_CONNECT_TIMEOUT_SECONDS
        connection_options["options"] = (
            f'{database.query.get("options", "")} -c statement_timeout=10000 -c lock_timeout=3000'
        )
        pool_options = {"pool_size": 5, "max_overflow": 5, "pool_timeout": 3}

    app.extensions["database"] = create_engine(
        database_url,
        pool_pre_ping=True,
        hide_parameters=True,
        connect_args=connection_options,
        **pool_options
    )
    app.register_blueprint(health)
    configure_errors(app)
    app.register_blueprint(accounts)
    app.register_blueprint(events)
    app.register_blueprint(wishlists)
    register_commands(app)
    return app
