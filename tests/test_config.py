import pytest
from pydantic import ValidationError
from sqlalchemy.engine import make_url

from app.core.config import Settings


def test_windows_database_credentials_build_safe_url(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_USERNAME", "ai_up_user")
    monkeypatch.setenv("DATABASE_PASSWORD", "senha@local!2026")

    settings = Settings(_env_file=None)
    url = make_url(settings.database_url)

    assert url.username == "ai_up_user"
    assert url.password == "senha@local!2026"
    assert url.host == "localhost"
    assert url.database == "ai_up"


def test_process_database_url_has_precedence(monkeypatch) -> None:
    explicit_url = "sqlite+pysqlite:///explicit.db"
    monkeypatch.setenv("DATABASE_URL", explicit_url)
    monkeypatch.setenv("DATABASE_USERNAME", "ignored")
    monkeypatch.setenv("DATABASE_PASSWORD", "ignored")

    settings = Settings(_env_file=None)

    assert settings.database_url == explicit_url


def test_cors_rejects_wildcards_and_normalizes_explicit_origins(monkeypatch) -> None:
    monkeypatch.delenv("CORS_ALLOWED_ORIGINS", raising=False)
    with pytest.raises(ValidationError, match="origens HTTP.*explícitas"):
        Settings(_env_file=None, cors_allowed_origins=["*"])

    settings = Settings(
        _env_file=None,
        cors_allowed_origins=["https://app.empresa.com/", "https://app.empresa.com"],
    )
    assert settings.cors_allowed_origins == ["https://app.empresa.com"]


def test_bootstrap_token_requires_minimum_length(monkeypatch) -> None:
    monkeypatch.delenv("BOOTSTRAP_TOKEN", raising=False)
    with pytest.raises(ValidationError, match="pelo menos 24 caracteres"):
        Settings(_env_file=None, bootstrap_token="curto")
