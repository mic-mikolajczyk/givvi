from collections.abc import Iterator

from cryptography.fernet import Fernet
from flask import Flask
import pytest


@pytest.fixture
def app() -> Iterator[Flask]:
    from givvi import create_app

    application = create_app({"TESTING": True, "DATABASE_URL": "sqlite+pysqlite:///:memory:"})
    yield application
    application.extensions["database"].dispose()


@pytest.fixture
def account_app(app: Flask) -> Flask:
    from givvi.models import Base

    app.config.update(OUTBOX_KEY=Fernet.generate_key().decode(), COOKIE_SECURE=False)
    Base.metadata.create_all(app.extensions["database"])
    return app
