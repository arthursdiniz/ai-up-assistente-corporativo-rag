"""Offline, checksummed backup; restoration always uses a new database/directory."""
import argparse
from datetime import datetime, UTC
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts._environment import load_user_environment

load_user_environment()
from app.core.config import get_settings
from sqlalchemy.engine import make_url


def pg_environment():
    url = make_url(get_settings().database_url)
    if url.get_backend_name() != "postgresql":
        raise RuntimeError("Esta ferramenta opera sobre PostgreSQL.")
    env = os.environ.copy()
    env.update(PGHOST=url.host or "localhost", PGPORT=str(url.port or 5432),
               PGUSER=url.username or "postgres", PGPASSWORD=url.password or "")
    return url, env


def digest(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify(directory):
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    for relative, expected in manifest["sha256"].items():
        path = (directory / relative).resolve()
        if not path.is_relative_to(directory.resolve()) or digest(path) != expected:
            raise RuntimeError("Backup incompleto ou checksum inválido.")
    return manifest


def create():
    settings = get_settings()
    with socket.socket() as sock:
        sock.settimeout(1)
        if sock.connect_ex(("127.0.0.1", 8000)) == 0:
            raise RuntimeError("Encerre o AI-Up na porta 8000 antes do backup consistente.")
    directory = settings.resolve_path(Path("data/backups")) / datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    directory.mkdir(parents=True, exist_ok=False)
    url, env = pg_environment()
    subprocess.run(["pg_dump", "--format=custom", "--no-owner", "--file", str(directory / "database.dump"), url.database], env=env, check=True)
    for name, origin in (("uploads", settings.resolved_upload_dir), ("chroma", settings.resolved_chroma_dir)):
        if origin.exists():
            shutil.copytree(origin, directory / name)
    checksums = {path.relative_to(directory).as_posix(): digest(path) for path in directory.rglob("*") if path.is_file()}
    (directory / "manifest.json").write_text(json.dumps({"created_at":datetime.now(UTC).isoformat(), "sha256":checksums}, indent=2), encoding="utf-8")
    verify(directory)
    print(f"Backup verificado: {directory}")


def restore(directory, database, destination):
    import psycopg
    from psycopg import sql

    verify(directory)
    url, env = pg_environment()
    if not database.startswith("ai_up_restore_") or database == url.database or destination.exists():
        raise RuntimeError("Use um banco novo ai_up_restore_* e uma pasta que ainda não exista.")
    with psycopg.connect(host=env["PGHOST"], port=env["PGPORT"], user=env["PGUSER"], password=env["PGPASSWORD"], dbname="postgres", autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(database)))
    subprocess.run(["pg_restore", "--exit-on-error", "--no-owner", "--dbname", database, str(directory / "database.dump")], env=env, check=True)
    destination.mkdir(parents=True, exist_ok=False)
    for name in ("uploads", "chroma"):
        if (directory / name).exists():
            shutil.copytree(directory / name, destination / name)
    with psycopg.connect(host=env["PGHOST"], port=env["PGPORT"], user=env["PGUSER"], password=env["PGPASSWORD"], dbname=database) as connection:
        for document_id, filename in connection.execute("SELECT id, filename FROM documents"):
            connection.execute("UPDATE documents SET file_path = %s WHERE id = %s", (str((destination / "uploads" / filename).resolve()), document_id))
    print(f"Restauração concluída no banco {database} e em {destination}.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["create", "verify", "restore"])
    parser.add_argument("--backup", type=Path)
    parser.add_argument("--database")
    parser.add_argument("--destination", type=Path)
    args = parser.parse_args()
    if args.action == "create":
        create()
    elif not args.backup:
        parser.error("--backup é obrigatório")
    elif args.action == "verify":
        verify(args.backup)
        print("Backup íntegro.")
    elif not args.database or not args.destination:
        parser.error("--database e --destination são obrigatórios")
    else:
        restore(args.backup, args.database, args.destination)
