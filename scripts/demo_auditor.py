"""Start a disposable local Auditor instance with only synthetic data."""
import argparse
import os
from pathlib import Path
import secrets
import socket
import sys
from tempfile import TemporaryDirectory

import httpx
import uvicorn


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
EMAIL = "auditor@demo.aiup.local"
EXTERNAL_EMAIL = "externo@demo.aiup.local"
PASSWORD = "Demo-Auditor-2026!"


def run(directory, args, bound):
    url = f"sqlite+pysqlite:///{(directory / 'demo.sqlite3').as_posix()}"
    os.environ.update(DATABASE_URL=url, UPLOAD_DIR=str(directory / "uploads"), CHROMA_DIR=str(directory / "chroma"),
                      LLM_PROVIDER="ollama" if args.ollama else "mock", OLLAMA_BASE_URL="http://127.0.0.1:11434",
                      OLLAMA_MODEL="qwen3:4b-instruct", EMBEDDING_PROVIDER="sentence_transformers" if args.semantic else "hash",
                      AUDITOR_AUTOMATIC="false", AUDITOR_SEMANTIC="true" if args.semantic else "false",
                      AUDITOR_OLLAMA="false", BACKGROUND_PROCESSING="true",
                      APP_ENV="development", SECRET_KEY=secrets.token_urlsafe(48))
    if args.ollama:
        try:
            tags = httpx.get("http://127.0.0.1:11434/api/tags", timeout=5, trust_env=False)
            tags.raise_for_status()
            installed = {entry["name"] for entry in tags.json()["models"]}
        except (httpx.HTTPError, ValueError, KeyError) as exc:
            raise SystemExit("Inicie o Ollama local antes da demonstração real.") from exc
        if "qwen3:4b-instruct" not in installed:
            raise SystemExit("O modelo qwen3:4b-instruct deve estar disponível no Ollama.")

    from app.core.config import get_settings
    settings = get_settings()
    if (settings.database_url, settings.resolved_upload_dir, settings.resolved_chroma_dir) != (url, directory / "uploads", directory / "chroma"):
        raise SystemExit("A demonstração exige recursos temporários isolados.")

    from app.core.security import hash_password
    from app.db.base import Base
    from app.db.session import SessionLocal, engine
    from app.main import app
    from app.models.organization import Organization
    from app.models.user import User, UserRole
    from app.services.document_service import DocumentService

    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        organization = Organization(name="Empresa fictícia de demonstração")
        outside = Organization(name="Outra empresa fictícia")
        db.add_all([organization, outside])
        db.flush()
        password_hash = hash_password(PASSWORD)
        user = User(name="Auditor de demonstração", email=EMAIL, password_hash=password_hash,
                    organization_id=organization.id, role=UserRole.USER)
        external = User(name="Usuário externo", email=EXTERNAL_EMAIL, password_hash=password_hash,
                        organization_id=outside.id, role=UserRole.USER)
        db.add_all([user, external])
        db.commit()
        if args.sample:
            for name in ("v1/reembolso-viagens.txt", "circular-reembolso.txt", "excecao-viagem.txt"):
                path = ROOT / "evals" / "auditor_demo" / name
                DocumentService(settings).create_and_process(db, user, path.name, path.read_bytes(), None)
    settings.auditor_automatic = args.automatic
    settings.auditor_ollama = args.ollama
    print(f"Demonstração isolada: http://127.0.0.1:{bound.getsockname()[1]}/auditor.html", flush=True)
    print(f"Conta da instância descartável: {EMAIL} / {PASSWORD}", flush=True)
    print(f"Conta de outra organização: {EXTERNAL_EMAIL} (mesma senha da demonstração)", flush=True)
    try:
        uvicorn.Server(uvicorn.Config(app, log_level="warning")).run(sockets=[bound])
    finally:
        engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8013)
    parser.add_argument("--sample", action="store_true", help="Preload the two conflicting policies and one exception.")
    parser.add_argument("--automatic", action="store_true", help="Queue audits after new uploads are indexed.")
    parser.add_argument("--ollama", action="store_true", help="Use the locally installed Qwen instead of the chat mock.")
    parser.add_argument("--semantic", action="store_true", help="Use the configured Sentence Transformers model.")
    args = parser.parse_args()
    os.chdir(ROOT)
    with socket.socket() as bound:
        bound.bind(("127.0.0.1", args.port))
        with TemporaryDirectory(prefix="aiup-auditor-demo-", ignore_cleanup_errors=True) as name:
            run(Path(name).resolve(), args, bound)


if __name__ == "__main__":
    main()
