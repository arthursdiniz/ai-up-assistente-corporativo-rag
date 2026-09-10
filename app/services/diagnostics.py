from pathlib import Path
import shutil
import subprocess
import httpx
from sqlalchemy import text
from app.core.config import get_settings


def inspect_services(db):
    settings = get_settings()
    checks = []
    try:
        db.execute(text("SELECT 1"))
        checks.append({"name":"PostgreSQL", "status":"ok", "detail":"Conexão disponível"})
    except Exception:
        db.rollback()
        checks.append({"name":"PostgreSQL", "status":"error", "detail":"Confira o serviço e as credenciais nas variáveis de ambiente."})
    if settings.llm_provider == "mock":
        checks.append({"name":"Inteligência artificial", "status":"warning", "detail":"Modo de teste: configure LLM_PROVIDER=ollama para respostas reais."})
    else:
        try:
            response = httpx.get(settings.ollama_base_url + "/api/tags", timeout=4)
            response.raise_for_status()
            available = {item["name"] for item in response.json().get("models", [])}
            found = settings.ollama_model in available or settings.ollama_model + ":latest" in available
            checks.append({"name":"Ollama", "status":"ok" if found else "error", "detail":settings.ollama_model if found else f"Baixe o modelo configurado: {settings.ollama_model}"})
        except (httpx.HTTPError, ValueError, KeyError):
            checks.append({"name":"Ollama", "status":"error", "detail":"Abra o Ollama e confira o modelo instalado."})
    ocr = settings.tesseract_cmd or shutil.which("tesseract")
    ocr_ready = False
    if ocr:
        try:
            result = subprocess.run([ocr, "--list-langs"], capture_output=True, text=True, timeout=5,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            ocr_ready = result.returncode == 0 and "por" in result.stdout.split()
        except (OSError, subprocess.TimeoutExpired):
            pass
    checks.append({"name":"Leitura de imagens", "status":"ok" if ocr_ready else "warning",
        "detail":"Tesseract com idioma português disponível." if ocr_ready else "Confira o Tesseract e o pacote de idioma por. Documentos digitais continuam funcionando."})
    cached = False
    if settings.embedding_provider != "hash":
        try:
            from huggingface_hub import try_to_load_from_cache
            cached = isinstance(try_to_load_from_cache(settings.embedding_model, "config.json"), str)
            cached = cached or Path(settings.embedding_model).is_dir()
        except (OSError, ValueError):
            pass
    checks.append({"name":"Busca semântica", "status":"ok" if cached else "warning",
        "detail":settings.embedding_model + " · configuração em cache local" if cached else
        ("Embeddings de teste: não usar para avaliar a qualidade real." if settings.embedding_provider == "hash" else "Modelo não confirmado no cache; o primeiro uso pode exigir download.")})
    try:
        free = shutil.disk_usage(settings.resolved_upload_dir).free / 1024**3
        checks.append({"name":"Armazenamento", "status":"ok" if free > 1 else "warning", "detail":f"{free:.1f} GB livres"})
    except OSError:
        checks.append({"name":"Armazenamento", "status":"error", "detail":"Pasta de documentos indisponível."})
    return {"checks":checks, "status":"error" if any(item["status"] == "error" for item in checks) else ("warning" if any(item["status"] == "warning" for item in checks) else "ok"), "max_upload_size_mb":settings.max_upload_size_mb}
