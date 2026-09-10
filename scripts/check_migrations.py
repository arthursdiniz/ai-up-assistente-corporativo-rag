"""Validate real PostgreSQL migrations on an explicitly selected isolated test DB."""
import os
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts._environment import load_user_environment
load_user_environment()
from app.core.config import get_settings
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from alembic import command
from alembic.config import Config
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from app.db.base import Base
import app.models


def main():
    url=make_url(get_settings().database_url)
    if url.get_backend_name() != "postgresql" or not url.database.startswith(("ai_up_test_","ai_up_restore_")):
        raise SystemExit("Configure DATABASE_URL para um banco PostgreSQL isolado ai_up_test_* ou ai_up_restore_*.")
    command.upgrade(Config("alembic.ini"),"head")
    engine=create_engine(url)
    with engine.begin() as connection:
        differences=compare_metadata(MigrationContext.configure(connection,opts={"compare_type":True,"compare_server_default":False}),Base.metadata)
        if differences:
            print("Divergências entre migrations e modelos:",differences)
            raise SystemExit(1)
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "20260910_0004"
        print("PostgreSQL: migrations e modelos compatíveis; tabelas:",len(inspect(connection).get_table_names()))


if __name__ == "__main__":
    main()
