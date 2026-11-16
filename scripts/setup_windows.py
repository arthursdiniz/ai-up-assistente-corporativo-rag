"""Prepare one complete, local Windows installation and optionally start it."""
import argparse
import ctypes
import json
import logging
import os
from pathlib import Path
import re
import secrets
import shutil
import sys
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.core.windows_setup import installation_dir
from scripts import run_local
from scripts.windows_bootstrap import (SetupError, command, consent, download, install_vendor, log,
                                       require_space, say, secure_directory, setup_lock, write_text)
from scripts.windows_postgres import prepare_database


EXAMPLE_DATABASE = "postgresql+psycopg://postgres:postgres@localhost:5432/ai_up"
POR_URL = "https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/4.1.0/por.traineddata"
POR_SHA256 = "c4932b937207a9514b7514d518b931a99938c02a28a5a5a553f8599ed58b7deb"
MODEL_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]*(?::[A-Za-z0-9][A-Za-z0-9._-]*)?\Z")
OLLAMA_INSTALLER = ("https://github.com/ollama/ollama/releases/download/v0.40.16/OllamaSetup.exe",
                    "84db4f756ddc9e091142a85cdc0f7ae5db68bc9b3e075f114388b326f8ed912d", "OllamaSetup-0.40.16.exe", 3)
TESSERACT_INSTALLER = ("https://github.com/UB-Mannheim/tesseract/releases/download/v5.4.0.20240606/tesseract-ocr-w64-setup-5.4.0.20240606.exe",
                      "c885fff6998e0608ba4bb8ab51436e1c6775c2bafc2559a19b423e18678b60c9", "TesseractSetup-5.4.exe", 1)
VC_INSTALLER = ("https://download.visualstudio.microsoft.com/download/pr/78d061c5-9ef3-42ab-98ed-3309d1095dc4/9C02C9ED120F671B900E6B9471D890E3B2414117A7E53F4AE2E855466FA2B7C9/VC_redist.x64.exe",
                "9c02c9ed120f671b900e6b9471d890e3b2414117a7e53f4ae2e855466fa2b7c9", "VC_redist-14.52-x64.exe", 1)


def vc_runtime_available():
    try:
        for name in ("msvcp140.dll", "vcruntime140.dll", "vcruntime140_1.dll"):
            ctypes.WinDLL(name, winmode=0x800)  # Search System32 only.
    except OSError:
        return False
    return True


def read_env(path):
    from dotenv import dotenv_values

    return {key.upper(): value for key, value in dotenv_values(path, interpolate=False).items() if value is not None}


def configured_database(user):
    return bool(user.get("DATABASE_URL") or (user.get("DATABASE_USERNAME") and user.get("DATABASE_PASSWORD")))


def new_project_env(template, basic):
    # Generated project file contains public defaults only. Keep generated credentials off synced folders.
    private_keys = {"DATABASE_URL", "DATABASE_USERNAME", "DATABASE_PASSWORD", "DATABASE_HOST", "DATABASE_PORT", "DATABASE_NAME",
                    "SECRET_KEY", "TESSERACT_CMD", "TESSERACT_DATA_DIR"}
    overrides = {"DEBUG": "false", "LLM_PROVIDER": "mock" if basic else "ollama"}
    if basic:
        overrides["EMBEDDING_PROVIDER"] = "hash"
    lines = []
    for line in template.splitlines():
        key = line.partition("=")[0]
        if key in private_keys:
            continue
        if key in overrides:
            line = f"{key}={overrides[key]}"
        lines.append(line)
    return "\n".join(lines) + "\n"


def file_value(value):
    # Single quoted dotenv values preserve Windows backslashes and spaces.
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def save_settings(path, settings):
    write_text(path, "".join(f"{key}={file_value(value)}\n" for key, value in sorted(settings.items())), replace=path.exists())


def prepare_config(home):
    from app.core.config import get_settings

    private_path = home / "settings.env"
    previous = read_env(private_path)
    private = dict(previous)
    project_file = ROOT / ".env"
    project_settings = read_env(project_file)
    explicit = {**project_settings, **{key.upper(): value for key, value in os.environ.items()}}
    existing = project_file.exists()
    if not configured_database(explicit) and not (home / "database.json").exists():
        for key, fallback in (("UPLOAD_DIR", "data/uploads"), ("CHROMA_DIR", "data/chroma")):
            path = ROOT / (explicit.get(key) or fallback)
            if path.exists() and any(item.name != ".gitkeep" for item in path.iterdir()):
                raise SetupError("Há uploads ou índices anteriores sem configuração de banco. Recupere o .env ou as credenciais originais.")
    if not configured_database(explicit):
        private["DATABASE_URL"] = prepare_database(home)
        explicit.pop("DATABASE_URL", None)
    elif (home / "database.json").is_file() and private.get("DATABASE_URL"):
        # An explicit later configuration may intentionally point to another server.
        # Start our cluster only when it is the effective database.
        if get_settings().database_url == private.get("DATABASE_URL"):
            private["DATABASE_URL"] = prepare_database(home)
    if explicit.get("DATABASE_URL") == EXAMPLE_DATABASE and not (explicit.get("DATABASE_PASSWORD") or os.environ.get("DATABASE_URL")):
        raise SetupError("O .env existente ainda aponta para a configuração de exemplo. Restaure as credenciais reais ou use uma cópia limpa do ZIP.")
    secret = explicit.get("SECRET_KEY", "")
    if len(secret) < 32 or secret.startswith("SUBSTITUIR"):
        private.setdefault("SECRET_KEY", secrets.token_urlsafe(48))
        # Repair an explicitly empty/template key at runtime without rewriting an existing .env.
        os.environ["SECRET_KEY"] = private["SECRET_KEY"]
    if previous != private or not private_path.exists():
        save_settings(private_path, private)
    if not existing:
        basic = False
        if "LLM_PROVIDER" not in explicit:
            say("Modo completo: modelos locais, busca semântica e OCR. Reserve 10–15 GB livres e, de preferência, 16 GB de RAM.")
            basic = consent("Este computador é limitado e você prefere o modo básico (respostas simuladas e busca de teste)?")
        template = (ROOT / ".env.example").read_text(encoding="utf-8")
        write_text(project_file, new_project_env(template, basic))
        say("Configuração inicial criada. A primeira conta será criada no navegador.")
    get_settings.cache_clear()
    return get_settings(), private_path, private


def ensure_model(settings, home):
    from app.core.config import is_cloud_model

    if settings.llm_provider != "ollama":
        say("Ollama: modo simulado selecionado. As respostas do chat não usam um modelo real.")
        return
    model = settings.ollama_model
    if not MODEL_NAME.fullmatch(model) or is_cloud_model(model) or any(part in {"", ".", ".."} for part in model.split("/")):
        raise SetupError("Nome do modelo Ollama inválido ou não local. Confira OLLAMA_MODEL.")
    base = settings.ollama_base_url.rstrip("/")
    default_address = base in {"http://localhost:11434", "http://127.0.0.1:11434"}
    if default_address and run_local.ollama_models(base) is None and not run_local.ollama_executable():
        install_vendor("Ollama", "Ollama.Ollama", "https://ollama.com/download/windows", home, OLLAMA_INSTALLER,
                       installed=run_local.ollama_executable)
    models = run_local.ensure_ollama(settings, start_local=True, require_model=False)
    if model in models or f"{model}:latest" in models:
        say(f"Ollama: modelo local {model} disponível.")
        return
    executable = run_local.ollama_executable()
    if not default_address or not executable:
        raise SetupError(f"Modelo ausente no Ollama configurado. Baixe {model} na instância local correspondente.")
    estimate = " (~2,5 GB para o modelo padrão; outros modelos variam)"
    if not consent(f"Baixar o modelo local {model}{estimate}?"):
        raise SetupError("Download do modelo recusado. O modo atual requer Ollama real.")
    model_home = Path(os.environ.get("OLLAMA_MODELS") or (Path.home() / ".ollama" / "models"))
    drive = next(path for path in (model_home, *model_home.parents) if path.exists())
    require_space(drive, 4)
    env = {**os.environ, "OLLAMA_HOST": "127.0.0.1:11434"}
    import subprocess
    result = subprocess.run([executable, "pull", model], env=env)
    if result.returncode:
        raise SetupError("Falha ao baixar o modelo Ollama. Confira rede e espaço e tente novamente.")
    run_local.ensure_ollama(settings, start_local=False)


def find_tesseract(configured):
    if configured:
        return shutil.which(configured) or (configured if Path(configured).is_file() else None)
    path = shutil.which("tesseract.exe")
    if path:
        return path
    for variable in ("ProgramFiles", "LOCALAPPDATA"):
        if root := os.environ.get(variable):
            for location in ("Tesseract-OCR", "Programs/Tesseract-OCR"):
                candidate = Path(root) / location / "tesseract.exe"
                if candidate.is_file():
                    return str(candidate)
    return None


def ensure_ocr(settings, home, private):
    executable = find_tesseract(settings.tesseract_cmd)
    if not executable and settings.tesseract_cmd:
        raise SetupError("TESSERACT_CMD aponta para um executável indisponível. Confira o caminho configurado.")
    if not executable:
        install_vendor("Tesseract OCR", "UB-Mannheim.TesseractOCR", "https://github.com/UB-Mannheim/tesseract/wiki", home, TESSERACT_INSTALLER,
                       installed=lambda: find_tesseract(None))
        executable = find_tesseract(None)
    if not executable:
        raise SetupError("Tesseract não encontrado. Conclua o instalador oficial e tente novamente.")
    directory = settings.tesseract_data_dir
    args = [executable, "--list-langs"] + (["--tessdata-dir", directory] if directory else [])
    langs = command(args)
    if langs.returncode or "por" not in langs.stdout.split():
        if directory and directory != str(home / "tessdata"):
            raise SetupError("O diretório TESSERACT_DATA_DIR configurado não contém o idioma por.")
        directory = str(home / "tessdata")
        target = Path(directory) / "por.traineddata"
        if not target.is_file():
            if not consent("Baixar os dados oficiais de OCR em português (~2 MB)?"):
                raise SetupError("O modo completo exige OCR em português.")
            target.parent.mkdir(exist_ok=True)
            download(POR_URL, POR_SHA256, target, 3 * 1024**2)
        langs = command([executable, "--list-langs", "--tessdata-dir", directory])
        if langs.returncode or "por" not in langs.stdout.split():
            raise SetupError("O Tesseract não conseguiu carregar o idioma português.")
    if not settings.tesseract_cmd:
        private["TESSERACT_CMD"] = executable
    if directory:
        private["TESSERACT_DATA_DIR"] = directory
    return executable, directory


def check_ocr(executable, directory):
    from PIL import Image, ImageDraw, ImageFont

    font = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts" / "arial.ttf"
    with TemporaryDirectory(prefix="aiup-ocr-") as temporary:
        path = Path(temporary) / "exemplo.png"
        image = Image.new("RGB", (720, 120), "white")
        draw = ImageDraw.Draw(image)
        draw.text((35, 22), "DOCUMENTO TESTE 2026", fill="black", font=ImageFont.truetype(str(font), 42))
        image.save(path)
        args = [executable, path, "stdout", "-l", "por", "--psm", "7"]
        if directory:
            args += ["--tessdata-dir", directory]
        result = command(args)
        if result.returncode or "2026" not in result.stdout:
            raise SetupError("O idioma português foi listado, mas falhou no teste de leitura de imagem.")


def embedding_cached(model):
    from huggingface_hub import try_to_load_from_cache

    def ready(path):
        # New and legacy Sentence Transformer repositories use one of these weight names.
        weights = any(item.is_file() for item in path.glob("*.safetensors")) or (path / "pytorch_model.bin").is_file()
        tokenizer = any((path / name).is_file() for name in ("tokenizer.json", "vocab.txt", "sentencepiece.bpe.model"))
        return weights and tokenizer and (path / "config.json").is_file()

    if Path(model).is_dir():
        return ready(Path(model))
    config = try_to_load_from_cache(model, "config.json")
    return isinstance(config, str) and ready(Path(config).parent)


def verify_ml(settings, marker, executable, directory, repair):
    from importlib.metadata import version
    from app.services.embedding_service import EmbeddingService

    for path in (settings.resolved_upload_dir, settings.resolved_chroma_dir):
        path.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix="aiup-write-", dir=path):
            pass
    embedding_ready = settings.embedding_provider == "hash" or embedding_cached(settings.embedding_model)
    expected = {"schema": 1, "python": sys.version, "packages": {name: version(name) for name in
                ("chromadb", "torch", "sentence-transformers", "transformers", "Pillow", "psycopg", "fastapi", "uvicorn", "alembic")},
                "embedding": [settings.embedding_provider, settings.embedding_model],
                "ollama": [settings.llm_provider, settings.ollama_base_url, settings.ollama_model],
                "ocr": [executable, directory, Path(executable).stat().st_mtime_ns if executable else None]}
    previous = json.loads(marker.read_text(encoding="utf-8")) if marker.exists() else {}
    if not repair and embedding_ready and expected == previous:
        say("Diagnóstico local já validado para esta configuração.")
        return
    if not embedding_ready:
        if not consent(f"Baixar os embeddings de {settings.embedding_model} (cerca de 0,5 GB no modelo padrão)?"):
            raise SetupError("O download do modelo de embeddings é necessário para a busca semântica.")
        from huggingface_hub.constants import HF_HUB_CACHE
        cache = Path(HF_HUB_CACHE)
        require_space(next(path for path in (cache, *cache.parents) if path.exists()), 2)
    say("Testando imports, embeddings e ChromaDB com dados descartáveis...")
    import chromadb
    import fastapi, uvicorn, pymupdf, docx, openpyxl, psycopg, torch  # noqa: F401

    vector = EmbeddingService(settings).embed_query("Documento sintético de diagnóstico do AI-Up.")
    # Ephemeral client avoids touching the index of existing users or holding temporary files on Windows.
    store = chromadb.EphemeralClient().create_collection("install_" + secrets.token_hex(8))
    store.add(ids=["check"], embeddings=[vector])
    if store.query(query_embeddings=[vector], n_results=1)["ids"] != [["check"]]:
        raise SetupError("O teste de gravação e leitura no ChromaDB falhou.")
    if executable:
        check_ocr(executable, directory)
    if settings.llm_provider == "ollama":
        import httpx
        say("Testando uma geração curta no Ollama local...")
        try:
            response = httpx.post(settings.ollama_base_url.rstrip("/") + "/api/chat", timeout=180, trust_env=False,
                json={"model": settings.ollama_model, "messages": [{"role": "user", "content": "Responda apenas OK."}],
                      "stream": False, "options": {"num_predict": 32}})
            response.raise_for_status()
            if not response.json().get("message", {}).get("content", "").strip():
                raise ValueError("empty")
        except (httpx.HTTPError, ValueError, AttributeError) as exc:
            raise SetupError("O modelo está instalado, mas a geração de teste falhou. Confira a memória e o diagnóstico do Ollama.") from exc
    write_text(marker, json.dumps(expected), replace=marker.exists())
    say("Diagnósticos dos componentes concluídos.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", action="store_true")
    parser.add_argument("--demo", action="store_true", help="Cria contas de demonstração somente quando solicitado.")
    args = parser.parse_args()
    os.chdir(ROOT)
    home = installation_dir(ROOT)
    if home is None:
        raise SetupError("Instalador disponível apenas em Windows com perfil de usuário local.")
    if ctypes.windll.shell32.IsUserAnAdmin():
        raise SetupError("Abra o atalho com sua conta normal. Os instaladores externos pedem UAC quando necessário.")
    if args.start and not args.demo and run_local.reuse_running_server():
        return
    secure_directory(home)
    handler = logging.FileHandler(home / "setup.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    log.propagate = False
    with setup_lock(home / "setup.lock"):
        say("Preparando o AI-Up para Windows...")
        print(f"Log da instalação: {home / 'setup.log'}", flush=True)
        if not vc_runtime_available():
            install_vendor("runtime Visual C++ x64", "Microsoft.VCRedist.2015+.x64",
                           "https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist",
                           home, VC_INSTALLER, installed=vc_runtime_available)
            if not vc_runtime_available():
                raise SetupError("O runtime Visual C++ ainda não está disponível. Reinicie se foi solicitado e tente novamente.")
        settings, private_path, private = prepare_config(home)
        from sqlalchemy.engine import make_url
        if make_url(settings.database_url).get_backend_name() != "postgresql":
            raise SetupError("O instalador completo exige uma configuração PostgreSQL.")
        say("Validando a conexão PostgreSQL e as migrations...")
        run_local.main(["--migrate-only", *(["--demo"] if args.demo else [])])
        ensure_model(settings, home)
        executable, directory = None, None
        if settings.llm_provider == "ollama" or settings.embedding_provider != "hash":
            executable, directory = ensure_ocr(settings, home, private)
            if private != read_env(private_path):
                save_settings(private_path, private)
            if not settings.tesseract_cmd:
                os.environ["TESSERACT_CMD"] = executable
            if directory and not settings.tesseract_data_dir:
                os.environ["TESSERACT_DATA_DIR"] = directory
        verify_ml(settings, home / "diagnostics.json", executable, directory, repair=not args.start)
        say("Instalação pronta.")
    if args.start:
        from app.core.config import get_settings
        get_settings.cache_clear()
        if not run_local.reuse_running_server():
            say(f"AI-Up em {run_local.BROWSER_URL}. Pressione Ctrl+C para encerrar.")
            run_local.run_server(desktop=True)


if __name__ == "__main__":
    try:
        main()
    except SetupError as exc:
        log.error("Interrompido: %s", exc)
        raise SystemExit(str(exc)) from None
    except SystemExit as exc:
        if exc.code:
            log.error("Uma etapa de inicialização foi interrompida.")
        raise
    except Exception as exc:
        log.error("Falha na preparação (%s)", type(exc).__name__)
        raise SystemExit("Falha na preparação. Confira a etapa acima, o espaço e as permissões, e execute novamente.") from None
