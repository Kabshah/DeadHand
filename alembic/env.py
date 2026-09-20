"""alembic/env.py — Alembic migration environment (sync, for autogenerate support)."""
from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Import models so autogenerate can detect them
from app.switches.models import Base  # noqa: E402
from app.core.config import settings  # noqa: E402

target_metadata = Base.metadata

# Build sync URL for alembic:
#   postgresql+asyncpg://... -> postgresql+psycopg2://...
#   sqlite+aiosqlite:///...  -> sqlite:///...
_db_url = settings.DATABASE_URL
_sync_url = (
    _db_url.replace("+asyncpg", "", 1)
           .replace("+aiosqlite", "", 1)
)
config.set_main_option("sqlalchemy.url", _sync_url)


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
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
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
