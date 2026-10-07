from flask import Flask
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url

from givvi.health import health

DATABASE_CONNECT_TIMEOUT_SECONDS = 3


def create_app(config: dict[str, object] | None = None) -> Flask:
    """Build an independently configured application instance."""
    app = Flask(__name__)
    app.config.from_mapping(DEBUG=False)
    app.config.from_prefixed_env(prefix="GIVVI")
    if config is not None:
        app.config.update(config)

    database_url = app.config.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("GIVVI_DATABASE_URL must be configured")

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
    return app
