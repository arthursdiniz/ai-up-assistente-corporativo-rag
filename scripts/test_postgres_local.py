"""Run tests on a newly created PostgreSQL test database; never reuse a database."""
from datetime import datetime, UTC
from pathlib import Path
import os
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scripts._environment import load_user_environment
load_user_environment()
from app.core.config import get_settings
from sqlalchemy.engine import make_url
import psycopg
from psycopg import sql


def main():
    configured=make_url(get_settings().database_url)
    name="ai_up_test_"+datetime.now(UTC).strftime("%Y%m%d_%H%M%S_%f")
    with psycopg.connect(host=configured.host,port=configured.port or 5432,user=configured.username,
            password=configured.password,dbname="postgres",autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(name)))
    env=os.environ.copy()
    env["DATABASE_URL"]=configured.set(database=name).render_as_string(hide_password=False)
    env["TEST_DATABASE_URL"]=env["DATABASE_URL"]
    # Test fixtures only access the prefixed isolated database and temporary files.
    print("Banco isolado de testes:",name,flush=True)
    migration=subprocess.run([sys.executable,"scripts/check_migrations.py"],env=env)
    if migration.returncode:
        raise SystemExit(migration.returncode)
    result=subprocess.run([sys.executable,"-B","-m","pytest","-q","-p","no:cacheprovider"],env=env)
    print("Banco de teste preservado para inspeção:",name,flush=True)
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
