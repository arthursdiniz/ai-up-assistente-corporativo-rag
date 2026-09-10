"""Start the configured local stack; migrations do not reset existing accounts."""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts._environment import load_user_environment
load_user_environment()

from app.core.config import get_settings
from sqlalchemy import create_engine, text
from alembic import command
from alembic.config import Config


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--demo",action="store_true",help="Cria contas demo ausentes, sem redefinir contas existentes.")
    parser.add_argument("--migrate-only",action="store_true")
    args=parser.parse_args()
    settings=get_settings()
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
        import httpx
        try:
            response=httpx.get(settings.ollama_base_url+"/api/tags",timeout=5)
            response.raise_for_status()
            names={item["name"] for item in response.json().get("models",[])}
            if settings.ollama_model not in names and settings.ollama_model+":latest" not in names:
                raise ValueError()
        except Exception:
            raise SystemExit("Abra o Ollama e instale o modelo configurado: "+settings.ollama_model)
    print("AI-Up: http://localhost:8000 — Ctrl+C para encerrar. Contas existentes preservadas.")
    import uvicorn
    uvicorn.run("app.main:app",host="127.0.0.1",port=8000)


if __name__ == "__main__":
    main()
