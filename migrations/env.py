from logging.config import fileConfig

from alembic import context
from alembic.util import CommandError
from sqlalchemy import engine_from_config, pool, text

from app.core.config import get_settings
from app.db.base import Base
from app import models  # noqa: F401


config = context.config
# Alembic usa ConfigParser, no qual "%" possui significado especial. Senhas com
# caracteres codificados em URL precisam escapar esse símbolo para não falhar.
config.set_main_option("sqlalchemy.url", get_settings().database_url.replace("%", "%%"))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
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
        if connection.dialect.name == "postgresql":
            locked = connection.scalar(text("SELECT pg_try_advisory_lock(1527451721, 9)"))
            if not locked:
                raise CommandError("Outra atualização já está aplicando migrations neste banco.")
            # Use a session lock so Alembic can still manage its own transaction.
            connection.commit()
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
