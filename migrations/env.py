"""Alembic environment.

Connection URL and target metadata are taken from the application's own
``core`` package so migrations always track the real models and the configured
database (SQLite locally, PostgreSQL in production). ``render_as_batch`` is
enabled so ALTER operations work on SQLite, keeping us PostgreSQL-compatible.
"""
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# Make the project importable when alembic runs from the repo root.
from core.config import settings
from core.models import Base

# Pull in every model module so all tables register on Base.metadata before
# autogenerate compares against the database.
import core.models  # noqa: F401
import core.competency.models  # noqa: F401

config = context.config

# Inject the application's database URL (overrides the placeholder in alembic.ini).
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=settings.DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
