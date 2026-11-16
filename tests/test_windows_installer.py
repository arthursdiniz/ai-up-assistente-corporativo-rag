from functools import lru_cache
from hashlib import sha256
from io import BytesIO
import json
import os
import socket
import ssl
from types import SimpleNamespace
from urllib.error import HTTPError, URLError
from zipfile import ZipInfo

import httpx
import psycopg
import pytest

from app.core.config import Settings
from app.services.extraction_service import ExtractionService
from PIL import Image
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
    assert not list(tmp_path.glob("*.partial"))


def test_existing_ollama_model_does_not_install_or_pull(monkeypatch, tmp_path):
    monkeypatch.setattr(setup_windows.run_local, "ollama_models", lambda _: {"qwen3:4b-instruct": "digest"})
    monkeypatch.setattr(setup_windows, "install_vendor", lambda *a: pytest.fail("installed Ollama was replaced"))
    monkeypatch.setattr(setup_windows, "consent", lambda _: pytest.fail("installed model was downloaded"))
    assert setup_windows.ensure_model(Settings(_env_file=None, llm_provider="ollama"), tmp_path) == "digest"


def test_unsafe_model_is_rejected_before_contacting_ollama(monkeypatch, tmp_path):
    monkeypatch.setattr(setup_windows.run_local, "ollama_models", lambda _: pytest.fail("invalid model reached Ollama"))
    settings = Settings(_env_file=None, llm_provider="ollama", ollama_model="qwen3;whoami")
    with pytest.raises(SetupError, match="Nome do modelo"):
        setup_windows.ensure_model(settings, tmp_path)


@pytest.mark.parametrize(("failure", "message"), [
    (URLError(TimeoutError()), "internet, proxy"),
    (URLError(ssl.SSLCertVerificationError()), "certificado"),
    (HTTPError("https://example.com/artifact", 404, "missing", {}, None), "HTTP 404"),
])
def test_download_failures_are_actionable(monkeypatch, tmp_path, failure, message):
    def inaccessible(*args, **kwargs):
        raise failure

    monkeypatch.setattr(windows_bootstrap, "urlopen", inaccessible)
    target = tmp_path / "installer.exe"
    target.write_bytes(b"previous")
    with pytest.raises(SetupError, match=message):
        windows_bootstrap.download("https://example.com/artifact", "unused", target, 1024)
    assert target.read_bytes() == b"previous"
    assert not list(tmp_path.glob("*.partial"))


def test_truncated_download_is_not_published(monkeypatch, tmp_path):
    class Truncated(BytesIO):
        headers = {"Content-Length": "8"}

        def geturl(self):
            return "https://example.com/file"

    monkeypatch.setattr(windows_bootstrap, "urlopen", lambda *a, **k: Truncated(b"partial"))
    target = tmp_path / "installer.exe"
    with pytest.raises(SetupError, match="incompleto"):
        windows_bootstrap.download("https://example.com/file", sha256(b"partial").hexdigest(), target, 1024)
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("name", ["pgsql/bin/../test", "pgsql/bin/NUL.exe", "pgsql/bin/alt:stream",
                                  "pgsql/bin/test. ", "pgsql/bin/link\x00.exe", "pgsql/bin/file\\test"])
def test_portable_archive_rejects_unsafe_members(name):
    entry = ZipInfo(name)
    with pytest.raises(SetupError, match="caminho inesperado"):
        windows_postgres.portable_members(SimpleNamespace(infolist=lambda: [entry]))


def test_portable_archive_rejects_windows_case_collisions():
    entries = [ZipInfo("pgsql/bin/Test.exe"), ZipInfo("pgsql/bin/test.EXE")]
    with pytest.raises(SetupError, match="caminho inesperado"):
        windows_postgres.portable_members(SimpleNamespace(infolist=lambda: entries))


@pytest.mark.parametrize("content", ["{", "{}", '{"bin":"relative","port":false}'])
def test_bad_postgres_state_never_initializes_empty_cluster(monkeypatch, tmp_path, content):
    record = tmp_path / "database.json"
    record.write_text(content, encoding="utf-8")
    monkeypatch.setattr(windows_postgres, "initialize", lambda *a: pytest.fail("invalid state must not create data"))
    with pytest.raises(SetupError, match="database.json"):
        windows_postgres.prepare_database(tmp_path)
    assert record.read_text() == content


def private_cluster(home):
    bin_dir = home / "bin"
    bin_dir.mkdir()
    for name in windows_postgres.PG_TOOLS:
        (bin_dir / name).touch()
    cluster = home / "cluster"
    cluster.mkdir()
    (cluster / "PG_VERSION").write_text("18")
    (cluster / "user_data").write_text("preserve")
    record = home / "database.json"
    record.write_text(json.dumps({"bin": str(bin_dir), "port": 55432, "password": "a" * 48}))
    return bin_dir, cluster, record


@pytest.mark.parametrize("allow_change", [True, False])
def test_private_cluster_conflict_only_moves_managed_endpoint(monkeypatch, tmp_path, allow_change):
    bin_dir, cluster, record = private_cluster(tmp_path)
    result = []
    monkeypatch.setattr(windows_postgres, "status", lambda *a: False)
    monkeypatch.setattr(windows_postgres, "port_available", lambda port: port != 55432)
    monkeypatch.setattr(windows_postgres, "start", lambda *a: result.append(a))
    monkeypatch.setattr(windows_postgres, "initialize", lambda *a: pytest.fail("must not reinitialize"))

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def execute(self, sql):
            assert sql == "SELECT 1"

    monkeypatch.setattr(psycopg, "connect", lambda **k: Connection())
    if allow_change:
        assert ":55433/ai_up" in windows_postgres.prepare_database(tmp_path)
        assert result == [(bin_dir, cluster, 55433)]
        assert windows_postgres.read_state(record)["port"] == 55433
    else:
        with pytest.raises(SetupError, match="porta 55432"):
            windows_postgres.prepare_database(tmp_path, allow_port_change=False)
        assert result == []
        assert windows_postgres.read_state(record)["port"] == 55432
    assert (cluster / "user_data").read_text() == "preserve"
    assert windows_postgres.read_state(record)["password"] == "a" * 48


def test_port_probe_sees_a_real_loopback_listener():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        assert not windows_postgres.port_available(listener.getsockname()[1])


def test_invalid_pg_ctl_status_is_not_confused_with_stopped(monkeypatch, tmp_path):
    monkeypatch.setattr(windows_postgres, "command", lambda *a: SimpleNamespace(returncode=4))
    with pytest.raises(SetupError, match="código 4"):
        windows_postgres.status(tmp_path, tmp_path / "cluster")


def test_ollama_rejects_unrelated_http_200(monkeypatch):
    monkeypatch.setattr(setup_windows.run_local.httpx, "get", lambda *a, **k:
                        httpx.Response(200, json={"ok": True}, request=httpx.Request("GET", "http://localhost")))
    assert setup_windows.run_local.ollama_models("http://localhost") is None


def test_ollama_pull_uses_configured_local_port(monkeypatch, tmp_path):
    settings = Settings(_env_file=None, llm_provider="ollama", ollama_base_url="http://127.0.0.1:12034")
    monkeypatch.setattr(setup_windows.run_local, "ollama_models", lambda _: {})
    monkeypatch.setattr(setup_windows.run_local, "ensure_ollama",
                        lambda settings, start_local, **k: {} if start_local else {settings.ollama_model: "digest"})
    monkeypatch.setattr(setup_windows.run_local, "ollama_executable", lambda: "ollama.exe")
    monkeypatch.setattr(setup_windows, "require_space", lambda *a: None)
    monkeypatch.setattr(setup_windows, "consent", lambda _: True)

    def run(args, *, env, **kwargs):
        assert args == ["ollama.exe", "pull", settings.ollama_model]
        assert env["OLLAMA_HOST"] == "127.0.0.1:12034"
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(setup_windows, "command", run)
    assert setup_windows.ensure_model(settings, tmp_path) == "digest"


def test_managed_ocr_recovers_corrupt_language_even_if_listed(monkeypatch, tmp_path):
    tessdata = tmp_path / "tessdata"
    tessdata.mkdir()
    language = tessdata / "por.traineddata"
    language.write_bytes(b"broken")
    settings = Settings(_env_file=None, tesseract_data_dir=str(tessdata))
    monkeypatch.setattr(setup_windows, "find_tesseract", lambda _: "tesseract.exe")
    monkeypatch.setattr(setup_windows, "command", lambda *a: SimpleNamespace(returncode=0, stdout="por"))
    monkeypatch.setattr(setup_windows, "consent", lambda _: True)
    monkeypatch.setattr(setup_windows, "download", lambda url, digest, target, limit: target.write_bytes(b"restored"))
    assert setup_windows.ensure_ocr(settings, tmp_path, {}) == ("tesseract.exe", str(tessdata))
    assert language.read_bytes() == b"restored"


def test_chroma_corruption_is_reported_without_reset(tmp_path):
    settings = Settings(_env_file=None, chroma_dir=tmp_path / "chroma", upload_dir=tmp_path / "uploads")
    settings.chroma_dir.mkdir()
    index = settings.chroma_dir / "chroma.sqlite3"
    index.write_bytes(b"incomplete database")
    with pytest.raises(SetupError, match="ChromaDB"):
        setup_windows.verify_data_dirs(settings, full_check=False)
    assert index.read_bytes() == b"incomplete database"


def test_upload_dir_failure_is_explained(tmp_path):
    blocked = tmp_path / "uploads"
    blocked.write_bytes(b"keep file")
    settings = Settings(_env_file=None, chroma_dir=tmp_path / "chroma", upload_dir=blocked)
    with pytest.raises(SetupError, match="gravar"):
        setup_windows.verify_data_dirs(settings, full_check=False)
    assert blocked.read_bytes() == b"keep file"


def test_embeddings_signature_changes_when_weights_change(tmp_path):
    (tmp_path / "config.json").write_text("{}")
    (tmp_path / "tokenizer.json").write_text("{}")
    weights = tmp_path / "model.safetensors"
    weights.write_bytes(b"original")
    original = setup_windows.embedding_signature(str(tmp_path))
    weights.write_bytes(b"truncated")
    assert setup_windows.embedding_signature(str(tmp_path)) != original


def test_ocr_passes_windows_language_path_as_one_literal_argument(monkeypatch, tmp_path):
    import app.services.extraction_service as extraction

    directory = str(tmp_path / "língua portuguesa")
    monkeypatch.setattr(extraction.shutil, "which", lambda _: "tesseract.exe")

    def run(args, *, input, **kwargs):
        assert args == ["tesseract.exe", "stdin", "stdout", "-l", "por", "--tessdata-dir", directory]
        assert input.startswith(b"\x89PNG\r\n")
        return SimpleNamespace(returncode=0, stdout="Política".encode("utf-8"))

    monkeypatch.setattr(extraction.subprocess, "run", run)
    ocr = ExtractionService(Settings(_env_file=None, tesseract_data_dir=directory))
    assert ocr.read_image_text(Image.new("RGB", (40, 20))) == "Política"


@pytest.mark.parametrize(("installation", "status", "message"), [
    ("other", "ok", "outra instalação"),
    ("same", "degraded", "banco não está pronto"),
    ("same", "ok", None),
])
def test_reuse_only_opens_healthy_matching_installation(monkeypatch, installation, status, message):
    from contextlib import nullcontext

    run_local = setup_windows.run_local
    monkeypatch.setattr(run_local.socket, "create_connection", lambda *a, **k: nullcontext())
    monkeypatch.setattr(run_local, "installation_key", lambda _: "same")
    opened = []
    monkeypatch.setattr(run_local, "open_browser", lambda: opened.append(True))
    def get(url, **kwargs):
        data = {"paths": {path: {} for path in ("/api/health", "/api/chats", "/api/documents")}} if url.endswith("openapi.json") else {"status": status}
        return httpx.Response(200, json=data, headers={"X-AI-Up-Installation": installation}, request=httpx.Request("GET", url))

    monkeypatch.setattr(run_local.httpx, "get", get)
    if message:
        with pytest.raises(SystemExit, match=message):
            run_local.reuse_running_server()
        assert not opened
    else:
        assert run_local.reuse_running_server()
        assert opened == [True]


def test_interrupted_postgres_provisioning_retains_pending_credentials(monkeypatch, tmp_path):
    _, _, record = private_cluster(tmp_path)
    state = windows_postgres.read_state(record)
    state["admin"] = "b" * 48
    record.write_text(json.dumps(state))
    monkeypatch.setattr(windows_postgres, "status", lambda *a: True)
    monkeypatch.setattr(windows_postgres, "provision_role", lambda *a: None)

    def failed_auth(**kwargs):
        raise psycopg.OperationalError("synthetic failure")

    monkeypatch.setattr(psycopg, "connect", failed_auth)
    with pytest.raises(SetupError, match="validar o banco privado"):
        windows_postgres.prepare_database(tmp_path)
    assert windows_postgres.read_state(record) == state


def test_model_probe_checks_generation_and_digest_even_after_valid_start(monkeypatch, tmp_path):
    settings = Settings(_env_file=None, embedding_provider="hash", llm_provider="ollama",
                        chroma_dir=tmp_path / "chroma", upload_dir=tmp_path / "uploads")
    marker = tmp_path / "diagnostics.json"
    marker.write_text("{")
    calls = []

    def respond(url, **kwargs):
        calls.append(url)
        return httpx.Response(200, json={"message": {"content": "OK" if len(calls) == 1 else ""}},
                              request=httpx.Request("POST", url))

    monkeypatch.setattr(httpx, "post", respond)
    setup_windows.verify_ml(settings, marker, None, None, repair=False, ollama_digest="first")
    setup_windows.verify_ml(settings, marker, None, None, repair=False, ollama_digest="first")
    assert len(calls) == 1
    with pytest.raises(SetupError, match="geração de teste falhou"):
        setup_windows.verify_ml(settings, marker, None, None, repair=False, ollama_digest="second")
    assert json.loads(marker.read_text())["ollama"][-1] == "first"


@pytest.mark.skipif(os.name != "nt", reason="NTFS security descriptor")
def test_private_directory_and_existing_secret_replace_explicit_acl(tmp_path):
    home = tmp_path / "AI-Up" / "installations" / "audit"
    home.mkdir(parents=True)
    secret_file = home / "settings.env"
    secret_file.write_text("SYNTHETIC=1")
    for path in (home, secret_file):
        granted = windows_bootstrap.command(["icacls.exe", path, "/grant", "*S-1-1-0:R"])
        assert granted.returncode == 0
    windows_bootstrap.secure_directory(home)
    powershell = os.path.join(os.environ["SystemRoot"], "System32", "WindowsPowerShell", "v1.0", "powershell.exe")
    script = """
$ErrorActionPreference = 'Stop'
$expected = @([Security.Principal.WindowsIdentity]::GetCurrent().User.Value, 'S-1-5-18')
$root = $env:AIUP_TEST_ACL_PATH
foreach ($acl in @([IO.Directory]::GetAccessControl($root), [IO.File]::GetAccessControl([IO.Path]::Combine($root, 'settings.env')))) {
    $rules = $acl.GetAccessRules($true, $true, [Security.Principal.SecurityIdentifier])
    if (($rules.Count -ne 2) -or ($rules | Where-Object { $_.IdentityReference.Value -notin $expected })) { exit 1 }
}
"""
    result = windows_bootstrap.command([powershell, "-NoProfile", "-NonInteractive", "-Command", script],
                                       env={**os.environ, "AIUP_TEST_ACL_PATH": str(home)})
    assert result.returncode == 0
    assert secret_file.read_text() == "SYNTHETIC=1"
