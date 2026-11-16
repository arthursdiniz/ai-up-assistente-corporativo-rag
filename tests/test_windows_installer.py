from functools import lru_cache
from hashlib import sha256
from io import BytesIO
import pytest

from app.core.config import Settings
from scripts import setup_windows, windows_bootstrap, windows_postgres
from scripts.windows_bootstrap import SetupError


def config_fixture(monkeypatch, tmp_path):
    root = tmp_path / "Instalação com espaços"
    root.mkdir()
    home = tmp_path / "private"
    home.mkdir()
    (root / ".env.example").write_text(
        "DEBUG=true\nDATABASE_URL=example\nSECRET_KEY=example\nLLM_PROVIDER=mock\nEMBEDDING_PROVIDER=sentence_transformers\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(setup_windows, "ROOT", root)
    for key in ("DATABASE_URL", "DATABASE_USERNAME", "DATABASE_PASSWORD", "SECRET_KEY", "LLM_PROVIDER",
                "EMBEDDING_PROVIDER", "UPLOAD_DIR", "CHROMA_DIR"):
        monkeypatch.delenv(key, raising=False)

    @lru_cache
    def settings():
        return Settings(_env_file=(home / "settings.env", root / ".env"))

    monkeypatch.setattr("app.core.config.get_settings", settings)
    monkeypatch.setattr(setup_windows, "consent", lambda _: False)
    return root, home


def test_fresh_config_uses_private_credentials_and_is_idempotent(monkeypatch, tmp_path):
    root, home = config_fixture(monkeypatch, tmp_path)
    test_url = "postgresql+psycopg://aiup_app:synthetic-only@127.0.0.1:55432/ai_up"
    monkeypatch.setattr(setup_windows, "prepare_database", lambda _: test_url)
    settings, private_file, _ = setup_windows.prepare_config(home)
    assert settings.database_url == test_url and settings.llm_provider == "ollama" and not settings.debug
    assert len(settings.secret_key) >= 32
    shared = root / ".env"
    assert settings.secret_key not in shared.read_text() and "synthetic-only" not in shared.read_text()
    marker = private_file.stat().st_mtime_ns, shared.stat().st_mtime_ns
    monkeypatch.delenv("SECRET_KEY")  # A new launcher process.
    assert setup_windows.prepare_config(home)[0].secret_key == settings.secret_key
    assert marker == (private_file.stat().st_mtime_ns, shared.stat().st_mtime_ns)


def test_existing_configuration_is_preserved(monkeypatch, tmp_path):
    root, home = config_fixture(monkeypatch, tmp_path)
    content = ("DATABASE_URL=postgresql+psycopg://legacy:synthetic@127.0.0.1:5432/existing\n"
               "SECRET_KEY=" + "x" * 48 + "\nLLM_PROVIDER=mock\n")
    (root / ".env").write_text(content, encoding="utf-8")
    monkeypatch.setattr(setup_windows, "prepare_database", lambda _: pytest.fail("existing DB was replaced"))
    settings, _, _ = setup_windows.prepare_config(home)
    assert settings.llm_provider == "mock" and settings.database_url.endswith("/existing")
    assert (root / ".env").read_text() == content


def test_data_without_configuration_stops_before_provisioning(monkeypatch, tmp_path):
    root, home = config_fixture(monkeypatch, tmp_path)
    existing = root / "data" / "uploads" / "original.txt"
    existing.parent.mkdir(parents=True)
    existing.write_text("synthetic", encoding="utf-8")
    monkeypatch.setattr(setup_windows, "prepare_database", lambda _: pytest.fail("orphaned data must block provisioning"))
    with pytest.raises(SetupError, match="uploads ou índices"):
        setup_windows.prepare_config(home)
    assert existing.read_text() == "synthetic"


def test_discovery_reuses_existing_postgres_binaries(monkeypatch, tmp_path):
    program_files = tmp_path / "Program Files"
    pg = program_files / "PostgreSQL" / "18" / "bin"
    pg.mkdir(parents=True)
    for name in windows_postgres.PG_TOOLS:
        (pg / name).touch()
    monkeypatch.setenv("ProgramFiles", str(program_files))
    monkeypatch.setattr(windows_postgres.shutil, "which", lambda _: None)
    assert windows_postgres.discover_bin(tmp_path / "state") == pg


def test_vendor_refusal_never_downloads_or_executes(monkeypatch, tmp_path):
    monkeypatch.setattr(windows_bootstrap.shutil, "which", lambda _: "winget.exe")
    monkeypatch.setattr(windows_bootstrap, "consent", lambda _: False)
    monkeypatch.setattr(windows_bootstrap, "command", lambda *a, **k: pytest.fail("installer executed"))
    monkeypatch.setattr(windows_bootstrap, "download", lambda *a, **k: pytest.fail("installer downloaded"))
    assert not windows_bootstrap.install_vendor("Test", "Vendor.Test", "https://example.com", tmp_path, ())


@pytest.mark.parametrize("valid", [True, False])
def test_verified_download_never_publishes_failed_checksum(monkeypatch, tmp_path, valid):
    class Response(BytesIO):
        def geturl(self):
            return "https://example.com/file"

    monkeypatch.setattr(windows_bootstrap, "urlopen", lambda *a, **k: Response(b"synthetic"))
    target = tmp_path / "test.exe"
    digest = sha256(b"synthetic" if valid else b"other").hexdigest()
    if valid:
        windows_bootstrap.download("https://example.com/file", digest, target, 1024)
        assert target.read_bytes() == b"synthetic"
    else:
        with pytest.raises(SetupError, match="SHA-256"):
            windows_bootstrap.download("https://example.com/file", digest, target, 1024)
        assert not target.exists()
    assert not target.with_suffix(".exe.partial").exists()


def test_existing_ollama_model_does_not_install_or_pull(monkeypatch, tmp_path):
    monkeypatch.setattr(setup_windows.run_local, "ollama_models", lambda _: {"qwen3:4b-instruct"})
    monkeypatch.setattr(setup_windows, "install_vendor", lambda *a: pytest.fail("installed Ollama was replaced"))
    monkeypatch.setattr(setup_windows, "consent", lambda _: pytest.fail("installed model was downloaded"))
    setup_windows.ensure_model(Settings(_env_file=None, llm_provider="ollama"), tmp_path)


def test_unsafe_model_is_rejected_before_contacting_ollama(monkeypatch, tmp_path):
    monkeypatch.setattr(setup_windows.run_local, "ollama_models", lambda _: pytest.fail("invalid model reached Ollama"))
    settings = Settings(_env_file=None, llm_provider="ollama", ollama_model="qwen3;whoami")
    with pytest.raises(SetupError, match="Nome do modelo"):
        setup_windows.ensure_model(settings, tmp_path)
