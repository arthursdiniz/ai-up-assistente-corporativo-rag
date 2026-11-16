"""Start the configured local stack; migrations do not reset existing accounts."""
import argparse
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
from threading import Event, Thread
import webbrowser

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts._environment import load_user_environment
load_user_environment()

from app.core.config import get_settings
from sqlalchemy import create_engine, text
from alembic import command
from alembic.config import Config
import httpx


HOST, PORT = "127.0.0.1", 8000
LOCAL_URL = f"http://{HOST}:{PORT}"
BROWSER_URL = f"http://localhost:{PORT}"


def open_browser():
    try:
        if webbrowser.open(BROWSER_URL, new=2):
            return
    except (OSError, webbrowser.Error):
        pass
    print(f"Abra {BROWSER_URL} no navegador.", flush=True)


def reuse_running_server():
    try:
        with socket.create_connection((HOST, PORT), timeout=1):
            pass
    except (ConnectionRefusedError, TimeoutError):
        # A free loopback port on Windows can time out before refusing the connection.
        return False
    try:
        response = httpx.get(f"{LOCAL_URL}/openapi.json", timeout=3, trust_env=False)
        response.raise_for_status()
        paths = response.json().get("paths", {})
        if {"/api/health", "/api/chats", "/api/documents"} <= paths.keys():
            print("O AI-Up ja esta em execucao.", flush=True)
            open_browser()
            return True
    except (httpx.HTTPError, ValueError, AttributeError):
        pass
    raise SystemExit(f"A porta {PORT} esta ocupada. Feche o programa que usa a porta e tente novamente.")


def ollama_models(base_url):
    try:
        result = httpx.get(base_url.rstrip("/") + "/api/tags", timeout=3, trust_env=False)
        result.raise_for_status()
        return {item["name"] for item in result.json().get("models", [])}
    except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError):
        return None


def ensure_ollama(settings, start_local):
    base_url = settings.ollama_base_url.rstrip("/")
    models = ollama_models(base_url)
    if models is None and start_local and base_url in ("http://localhost:11434", "http://127.0.0.1:11434"):
        local = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe"
        executable = str(local) if local.is_file() else shutil.which("ollama")
        if not executable:
            raise SystemExit("Ollama não encontrado. Instale ou abra o Ollama e tente novamente.")
        print("Iniciando Ollama local...", flush=True)
        try:
            subprocess.Popen([executable, "serve"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                             env={**os.environ, "OLLAMA_HOST": "127.0.0.1:11434"})
        except OSError as exc:
            raise SystemExit("Não foi possível iniciar o Ollama. Abra o Ollama manualmente e tente novamente.") from exc
        wait = Event()
        for _ in range(20):
            models = ollama_models(base_url)
            if models is not None:
                break
            wait.wait(0.5)
    if models is None:
        raise SystemExit(f"Ollama indisponível em {base_url}. Abra o Ollama e tente novamente.")
    model = settings.ollama_model
    if model not in models and f"{model}:latest" not in models:
        raise SystemExit(f"Modelo local ausente. Execute: ollama pull {model}")


def run_server(desktop):
    import uvicorn

    server = uvicorn.Server(uvicorn.Config("app.main:app", host=HOST, port=PORT))
    finished = Event()

    def open_when_ready():
        while not finished.wait(0.15):
            if server.started:
                open_browser()
                return

    if desktop:
        Thread(target=open_when_ready, daemon=True, name="ai-up-browser").start()
    try:
        server.run()
        if not server.started:
            raise SystemExit(1)
    finally:
        finished.set()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo",action="store_true",help="Cria contas demo ausentes, sem redefinir contas existentes.")
    parser.add_argument("--migrate-only",action="store_true")
    parser.add_argument("--desktop", action="store_true", help="Inicia serviços locais e abre o navegador.")
    args=parser.parse_args()
    settings=get_settings()
    if args.desktop and not args.migrate_only and not args.demo and reuse_running_server():
        return
    try:
        with create_engine(settings.database_url).connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        raise SystemExit("PostgreSQL indisponível. Confira o serviço e as variáveis de ambiente.")
    command.upgrade(Config("alembic.ini"),"head")
    if args.demo:
        from scripts.seed import seed
        seed()
    if args.migrate_only:
        return
    if settings.llm_provider == "ollama":
        ensure_ollama(settings, start_local=args.desktop)
    print(f"AI-Up: {BROWSER_URL} — Ctrl+C para encerrar. Contas existentes preservadas.", flush=True)
    run_server(args.desktop)


if __name__ == "__main__":
    main()
