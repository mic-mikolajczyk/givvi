import os

from alembic import context
from sqlalchemy import create_engine

from givvi.models import Base

config = context.config


def migrate(connection) -> None:
    context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    context.configure(url=os.environ["GIVVI_DATABASE_URL"], target_metadata=Base.metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
elif config.attributes.get("connection") is not None:
    migrate(config.attributes["connection"])
else:
    engine = create_engine(os.environ["GIVVI_DATABASE_URL"], hide_parameters=True)
    with engine.connect() as connection:
        migrate(connection)
    engine.dispose()
