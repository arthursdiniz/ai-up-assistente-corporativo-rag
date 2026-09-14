from functools import lru_cache
import os
import secrets
from urllib.parse import urlsplit
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "AI-Up"
    app_env: str = "development"
    debug: bool = False

    database_url: str = Field(
        default="postgresql+psycopg://postgres:postgres@localhost:5432/ai_up",
        repr=False,
    )
    database_username: str | None = None
    database_password: SecretStr | None = Field(default=None, repr=False)
    database_host: str = "localhost"
    database_port: int = 5432
    database_name: str = "ai_up"
    secret_key: str = Field(default="change-me", repr=False)
    access_token_expire_minutes: int = Field(default=30, ge=5, le=1440)
    refresh_token_expire_days: int = Field(default=14, ge=1, le=90)
    invitation_expire_hours: int = Field(default=72, ge=1, le=720)
    cors_allowed_origins: list[str] = Field(default_factory=list)
    bootstrap_token: SecretStr | None = Field(default=None, repr=False)

    upload_dir: Path = Path("./data/uploads")
    chroma_dir: Path = Path("./data/chroma")
    max_upload_size_mb: int = 20
    max_document_pages: int = Field(default=500, ge=1, le=5000)
    max_extracted_chars: int = Field(default=2000000, ge=1000)
    chunk_token_limit: int = Field(default=120, ge=16, le=1024)
    chunk_token_overlap: int = Field(default=20, ge=0)
    background_processing: bool = True
    login_attempt_limit: int = Field(default=8, ge=2)
    login_attempt_window_seconds: int = Field(default=300, ge=10)
    generation_workers: int = Field(default=2, ge=1, le=4)

    chunk_size: int = 1200
    chunk_overlap: int = 200
    rag_top_k: int = 5
    rag_min_relevance: float = Field(default=0.25, ge=0.0, le=1.0)
    rag_broad_top_k: int = Field(default=8, ge=3, le=20)
    rag_broad_min_relevance: float = Field(default=0.18, ge=0.0, le=1.0)
    rag_candidate_pool: int = Field(default=20, ge=5, le=100)
    rag_semantic_weight: float = Field(default=0.65, ge=0.0, le=1.0)
    rag_semantic_only_min_relevance: float = Field(default=0.50, ge=0.0, le=1.0)
    rag_lexical_scan_limit: int = Field(default=5000, ge=100, le=50000)
    conversation_history_messages: int = Field(default=6, ge=0, le=20)
    conversation_history_char_limit: int = Field(default=6000, ge=500, le=20000)

    llm_provider: Literal["mock", "ollama"] = "mock"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:4b-instruct"

    embedding_provider: Literal["sentence_transformers", "hash"] = "sentence_transformers"
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    tesseract_cmd: str | None = None

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    @model_validator(mode="after")
    def validate_settings(self) -> "Settings":
        if self.llm_provider == "ollama" and (urlsplit(self.ollama_base_url).hostname not in {"localhost", "127.0.0.1", "::1"} or self.ollama_model.endswith("-cloud")):
            raise ValueError("O modo privado exige Ollama local e um modelo sem sufixo -cloud.")
        if self.chunk_token_overlap >= self.chunk_token_limit:
            raise ValueError("CHUNK_TOKEN_OVERLAP deve ser menor que CHUNK_TOKEN_LIMIT.")
        if self.app_env != "development" and (len(self.secret_key) < 32 or self.secret_key.startswith("SUBSTITUIR")):
            raise ValueError("Configure SECRET_KEY com uma chave aleatória de pelo menos 32 caracteres.")
        if self.app_env == "development" and (len(self.secret_key) < 32 or self.secret_key.startswith("SUBSTITUIR")):
            self.secret_key = secrets.token_urlsafe(48)
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("CHUNK_OVERLAP deve ser menor que CHUNK_SIZE.")
        if self.rag_candidate_pool < self.rag_top_k:
            raise ValueError("RAG_CANDIDATE_POOL deve ser maior ou igual a RAG_TOP_K.")
        normalized_origins: list[str] = []
        for origin in self.cors_allowed_origins:
            candidate = origin.strip().rstrip("/")
            parsed = urlsplit(candidate)
            if (
                candidate == "*"
                or parsed.scheme not in {"http", "https"}
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.path
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError(
                    "CORS_ALLOWED_ORIGINS aceita somente origens HTTP(S) explícitas, sem caminhos ou wildcard."
                )
            if candidate not in normalized_origins:
                normalized_origins.append(candidate)
        self.cors_allowed_origins = normalized_origins
        if self.bootstrap_token and len(self.bootstrap_token.get_secret_value()) < 24:
            raise ValueError("BOOTSTRAP_TOKEN deve ter pelo menos 24 caracteres.")

        # A DATABASE_URL definida diretamente no processo tem precedência. Quando
        # ela não existe, as credenciais separadas do Windows substituem a URL de
        # exemplo presente no .env sem exigir que a senha seja gravada em arquivo.
        if not os.environ.get("DATABASE_URL") and self.database_username and self.database_password:
            self.database_url = URL.create(
                drivername="postgresql+psycopg",
                username=self.database_username,
                password=self.database_password.get_secret_value(),
                host=self.database_host,
                port=self.database_port,
                database=self.database_name,
            ).render_as_string(hide_password=False)
        return self

    def resolve_path(self, value: Path) -> Path:
        return value if value.is_absolute() else (PROJECT_ROOT / value).resolve()

    @property
    def resolved_upload_dir(self) -> Path:
        return self.resolve_path(self.upload_dir)

    @property
    def resolved_chroma_dir(self) -> Path:
        return self.resolve_path(self.chroma_dir)


@lru_cache
def get_settings() -> Settings:
    return Settings()
