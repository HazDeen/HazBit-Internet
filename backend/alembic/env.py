from __future__ import annotations

from logging.config import fileConfig

from alembic import context
from app.core.config import Settings
from app.database.base import Base
from sqlalchemy import engine_from_config, pool

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = Settings()
alembic_url = settings.database.alembic_url().render_as_string(hide_password=False)
config.set_main_option("sqlalchemy.url", alembic_url.replace("%", "%%"))

target_metadata = Base.metadata

if getattr(config.cmd_opts, "autogenerate", False):
    raise RuntimeError(
        "Alembic autogenerate is disabled while ORM metadata maps only active domains; "
        "create and review a manual revision to protect the remaining STEP 2 tables"
    )


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        version_table_schema="public",
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
            compare_server_default=True,
            version_table_schema="public",
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
