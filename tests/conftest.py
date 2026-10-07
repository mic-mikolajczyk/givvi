from collections.abc import Iterator

from flask import Flask
import pytest


@pytest.fixture
def app() -> Iterator[Flask]:
    from givvi import create_app

    application = create_app({"TESTING": True, "DATABASE_URL": "sqlite+pysqlite:///:memory:"})
    yield application
    application.extensions["database"].dispose()
