import os
from uuid import uuid4

from alembic import command
from alembic.config import Config
from cryptography.fernet import Fernet
import pytest
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.schema import CreateSchema
from sqlalchemy.schema import DropSchema

from givvi import create_app


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
