"""Alembic environment shared by SQLite development and PostgreSQL deployment."""

import os

from alembic import context
from sqlalchemy import engine_from_config, pool

from app.storage import Base

config = context.config
target_metadata = Base.metadata


def database_url() -> str:
    return os.environ.get("DATABASE_URL", config.get_main_option("sqlalchemy.url"))


def run_migrations_offline() -> None:
    context.configure(
        url=database_url(), target_metadata=target_metadata, literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    settings = config.get_section(config.config_ini_section) or {}
    settings["sqlalchemy.url"] = database_url()
    engine = engine_from_config(settings, prefix="sqlalchemy.", poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
