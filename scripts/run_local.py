"""Start the configured local stack; migrations do not reset existing accounts."""
import argparse
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
from threading import Event, Thread
from urllib.parse import urlsplit
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts._environment import load_user_environment
load_user_environment()

from app.core.windows_setup import installation_key
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
            try:
                health = httpx.get(f"{LOCAL_URL}/api/health", timeout=5, trust_env=False)
                health.raise_for_status()
                reported = health.json()
                if health.headers.get("X-AI-Up-Installation") != installation_key(ROOT):
                    raise SystemExit(f"A porta {PORT} está em uso por outra instalação ou versão do AI-Up. Feche a outra janela e tente novamente.")
                if reported.get("status") != "ok":
                    raise ValueError
            except (httpx.HTTPError, ValueError, AttributeError):
                raise SystemExit("O AI-Up já está em execução, mas o banco não está pronto. Confira a janela do servidor.") from None
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
        models = result.json()["models"]
        if not isinstance(models, list) or any(not isinstance(item.get("name"), str) for item in models):
            return None
        return {item["name"]: item.get("digest") for item in models}
    except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError):
        return None


def ollama_executable():
    local = Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Ollama" / "ollama.exe"
    return str(local) if local.is_file() else shutil.which("ollama")


def ollama_cli_host(base_url):
    address = urlsplit(base_url)
    if (address.scheme == "http" and address.hostname in {"localhost", "127.0.0.1", "::1"}
            and address.path in ("", "/") and not (address.username or address.query or address.fragment)):
        host = "[::1]" if address.hostname == "::1" else "127.0.0.1"
        return f"{host}:{address.port or 80}"
    return None


def ensure_ollama(settings, start_local, *, require_model=True):
    base_url = settings.ollama_base_url.rstrip("/")
    models = ollama_models(base_url)
    cli_host = ollama_cli_host(base_url)
    if models is None and start_local and cli_host:
        executable = ollama_executable()
        if not executable:
            raise SystemExit("Ollama não encontrado. Instale ou abra o Ollama e tente novamente.")
        print("Iniciando Ollama local...", flush=True)
        try:
            process = subprocess.Popen([executable, "serve"], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                             env={**os.environ, "OLLAMA_HOST": cli_host})
        except OSError as exc:
            raise SystemExit("Não foi possível iniciar o Ollama. Abra o Ollama manualmente e tente novamente.") from exc
        wait = Event()
        for _ in range(20):
            models = ollama_models(base_url)
            if models is not None:
                break
            if process.poll() is not None:
                raise SystemExit("O Ollama encerrou ao iniciar. Confira se a porta configurada está ocupada e abra o Ollama novamente.")
            wait.wait(0.5)
    if models is None:
        raise SystemExit("Ollama indisponível no endereço configurado. Abra o Ollama e tente novamente.")
    model = settings.ollama_model
    if require_model and model not in models and f"{model}:latest" not in models:
        raise SystemExit(f"Modelo local ausente. Execute: ollama pull {model}")
    return models


def run_server(desktop):
    import uvicorn

    server = uvicorn.Server(uvicorn.Config("app.main:app", host=HOST, port=PORT))
    finished = Event()

    def open_when_ready():
        while not finished.wait(0.15):
            if server.started:
                try:
                    health = httpx.get(f"{LOCAL_URL}/api/health", timeout=5, trust_env=False)
                    health.raise_for_status()
                    reported = health.json()
                    if reported.get("status") == "ok" and health.headers.get("X-AI-Up-Installation") == installation_key(ROOT):
                        open_browser()
                    else:
                        print("O AI-Up iniciou, mas o banco está indisponível. Confira o diagnóstico.", flush=True)
                except (httpx.HTTPError, ValueError, AttributeError):
                    print(f"Falha ao abrir automaticamente. Verifique {BROWSER_URL}/api/health.", flush=True)
                return

    if desktop:
        Thread(target=open_when_ready, daemon=True, name="ai-up-browser").start()
    try:
        server.run()
        if not server.started:
            raise SystemExit(1)
    finally:
        finished.set()


def main(argv=None):
    from alembic import command
    from alembic.config import Config
    from alembic.util import CommandError
    from sqlalchemy import create_engine, text
    from app.core.config import get_settings

    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo",action="store_true",help="Cria contas demo ausentes, sem redefinir contas existentes.")
    parser.add_argument("--migrate-only",action="store_true")
    parser.add_argument("--desktop", action="store_true", help="Inicia serviços locais e abre o navegador.")
    args=parser.parse_args(argv)
    settings=get_settings()
    if args.desktop and not args.migrate_only and not args.demo and reuse_running_server():
        return
    engine = None
    try:
        options = {"connect_args": {"connect_timeout": 5}} if settings.database_url.startswith("postgresql") else {}
        engine = create_engine(settings.database_url, **options)
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        raise SystemExit("PostgreSQL indisponível. Confira o serviço, a porta e as credenciais configuradas.") from None
    finally:
        if engine is not None:
            engine.dispose()
    try:
        command.upgrade(Config("alembic.ini"), "head")
    except CommandError:
        raise SystemExit("As migrations não puderam continuar. Confira se outra atualização está em andamento e se os arquivos do projeto estão completos.") from None
    except Exception as exc:
        from scripts.windows_bootstrap import log

        original = getattr(exc, "orig", None)
        log.error("Falha de migration (%s, SQLSTATE %s).", type(exc).__name__, getattr(original, "sqlstate", None))
        raise SystemExit("O banco respondeu, mas a atualização do esquema falhou. Confira permissões e restaure uma cópia somente se houver corrupção confirmada.") from None
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
