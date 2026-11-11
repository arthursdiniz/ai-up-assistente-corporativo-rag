"""Low-volume HTTP load test against an automatically isolated AI-Up instance."""
import argparse
import json
import os
import platform
import secrets
import socket
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Thread
from time import perf_counter, process_time, sleep

import httpx
import uvicorn

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.benchmark_retrieval import timings


def measure(workers, operations, operation):
    def perform(index):
        start = perf_counter()
        try:
            detail = operation(index)
            error = None
        except (httpx.HTTPError, RuntimeError, KeyError) as exc:
            detail = None
            error = (str(exc) if isinstance(exc, RuntimeError) else
                     f"HTTP {exc.response.status_code}" if isinstance(exc, httpx.HTTPStatusError) else type(exc).__name__)
        return {"ms": (perf_counter() - start) * 1000, "error": error, "detail": detail}

    start, cpu_start = perf_counter(), process_time()
    with ThreadPoolExecutor(max_workers=workers) as pool:
        rows = list(pool.map(perform, range(operations)))
    elapsed = perf_counter() - start
    passed = [row for row in rows if row["error"] is None]
    return {"workers": workers, "operations": operations, "errors": operations - len(passed),
            "error_rate": round(1 - len(passed) / operations, 4), "throughput_ops_s": round(operations / elapsed, 2),
            "client_and_server_cpu_seconds": round(process_time() - cpu_start, 4),
            "successful_latency": timings([row["ms"] for row in passed]), "results": rows}


def run(root, steps, operations, ollama_model):
    database_url = f"sqlite+pysqlite:///{(root / 'bench.sqlite3').as_posix()}"
    os.environ.update(DATABASE_URL=database_url, UPLOAD_DIR=str(root / "uploads"), CHROMA_DIR=str(root / "chroma"),
                      EMBEDDING_PROVIDER="hash", LLM_PROVIDER="ollama" if ollama_model else "mock", BACKGROUND_PROCESSING="false",
                      APP_ENV="development", SECRET_KEY=secrets.token_urlsafe(48))
    from app.core.config import get_settings, is_cloud_model

    if ollama_model:
        if is_cloud_model(ollama_model):
            raise RuntimeError("Escolha um modelo local.")
        base = "http://127.0.0.1:11434"
        response = httpx.get(f"{base}/api/tags", timeout=5, trust_env=False)
        response.raise_for_status()
        names = {item["name"] for item in response.json()["models"]}
        name = ollama_model if ":" in ollama_model else f"{ollama_model}:latest"
        if name not in names:
            raise RuntimeError("Modelo local ausente. O benchmark não baixa modelos.")
        os.environ.update(OLLAMA_BASE_URL=base, OLLAMA_MODEL=name, GENERATION_WORKERS="2")
    settings = get_settings()
    if (settings.database_url, settings.resolved_upload_dir, settings.resolved_chroma_dir) != (database_url, root / "uploads", root / "chroma"):
        raise RuntimeError("Os recursos do benchmark precisam apontar para a pasta temporária.")
    from app.core.security import hash_password
    from app.db.base import Base
    from app.db.session import SessionLocal, engine
    from app.main import app
    from app.models.organization import Organization
    from app.models.user import User, UserRole

    password = secrets.token_urlsafe(24)
    emails = [f"benchmark-{i}@aiup.local" for i in range(operations)]
    password_hash = hash_password(password)
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        organization = Organization(name="Organização sintética de benchmark")
        db.add(organization)
        db.flush()
        db.add_all(User(name=email, email=email, password_hash=password_hash, role=UserRole.USER,
                        organization_id=organization.id) for email in emails)
        db.commit()

    server = uvicorn.Server(uvicorn.Config(app, access_log=False, log_level="warning"))
    with socket.socket() as bound:
        bound.bind(("127.0.0.1", 0))
        port = bound.getsockname()[1]
        worker = Thread(target=server.run, kwargs={"sockets": [bound]}, daemon=True)
        worker.start()
        try:
            deadline = perf_counter() + 15
            while not server.started and worker.is_alive() and perf_counter() < deadline:
                sleep(0.05)
            if not server.started:
                raise RuntimeError("A instância isolada não iniciou.")
            with httpx.Client(base_url=f"http://127.0.0.1:{port}", trust_env=False, timeout=130 if ollama_model else 20) as client:
                def login(index):
                    result = client.post("/api/auth/login", json={"email": emails[index], "password": password})
                    result.raise_for_status()
                    return {"Authorization": f"Bearer {result.json()['access_token']}"}

                def upload(headers, key):
                    result = client.post("/api/documents", headers=headers, files={"file": (
                        f"politica-{key}.txt", f"Regra sintética {key}. Prazo de entrega é 45 dias corridos.".encode(), "text/plain")})
                    result.raise_for_status()
                    row = result.json()
                    if row["status"] != "READY":
                        raise RuntimeError("index_not_ready")
                    return row["id"]

                headers = [login(i) for i in range(operations)]
                chats = []
                for i, header in enumerate(headers):
                    did = upload(header, f"setup-{i}")
                    created = client.post("/api/chats", headers=header, json={"document_ids": [did]})
                    created.raise_for_status()
                    chats.append(created.json()["id"])

                def listing(i):
                    client.get("/api/documents", headers=headers[i]).raise_for_status()

                def retrieval(i):
                    response = client.post(f"/api/chats/{chats[i]}/messages", headers=headers[i],
                                           json={"message": "Qual é o prazo de entrega?"})
                    response.raise_for_status()
                    result = response.json()
                    if not result["sources"]:
                        raise RuntimeError("retrieval_missing_evidence")
                    return {"pipeline_retrieval_ms": result["metrics"]["retrieval_ms"]}

                def measured_login(i):
                    login(i)  # Keep tokens out of the report.

                def streamed_generation(i):
                    start = perf_counter()
                    path = f"/api/chats/{chats[i]}/generations"
                    response = client.post(path, headers=headers[i], json={"message": "Qual é o prazo de entrega?"})
                    response.raise_for_status()
                    generation_id = response.json()["id"]
                    first_ms = None
                    with client.stream("GET", f"{path}/{generation_id}/events", headers=headers[i]) as stream:
                        stream.raise_for_status()
                        for line in stream.iter_lines():
                            if not line.startswith("data: "):
                                continue
                            event = json.loads(line[6:])
                            if event["type"] == "delta" and first_ms is None:
                                first_ms = (perf_counter() - start) * 1000
                            if event["type"] in {"error", "cancelled"}:
                                raise RuntimeError(f"generation_{event['type']}")
                            if event["type"] == "done":
                                result = event["data"]["result"]
                                if not result or not result["sources"]:
                                    raise RuntimeError("generation_missing_evidence")
                                return {"first_sse_delta_ms": first_ms,
                                        "pipeline_retrieval_ms": result["metrics"]["retrieval_ms"]}
                    raise RuntimeError("generation_stream_incomplete")

                report = []
                for count in steps:
                    workloads = ({"rag_ollama_stream": streamed_generation} if ollama_model else
                                 {"login": measured_login, "document_list": listing,
                                  "upload_and_index": lambda i: upload(headers[i], f"load-{count}-{i}"),
                                  "rag_mock": retrieval})
                    for name, operation in workloads.items():
                        result = measure(count, operations, operation)
                        if name.startswith("rag_"):
                            result["pipeline_retrieval"] = timings([row["detail"]["pipeline_retrieval_ms"]
                                                                   for row in result["results"] if row["detail"]])
                        if ollama_model:
                            deltas = [row["detail"]["first_sse_delta_ms"] for row in result["results"]
                                      if row["detail"] and row["detail"]["first_sse_delta_ms"] is not None]
                            result["first_sse_delta"] = timings(deltas)
                            result["first_sse_delta_samples"] = len(deltas)
                        report.append({"workload": name, **result})
                        print(f"{name}, {count} concorrentes: {result['errors']} erros em {operations} operações", flush=True)
                return report
        finally:
            server.should_exit = True
            worker.join(timeout=15)
            engine.dispose()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workers", nargs="+", type=int, default=[1, 2, 4])
    parser.add_argument("--operations", type=int, default=12)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--ollama-model", help="Use an installed local model and measure the complete job and SSE path.")
    args = parser.parse_args()
    if not 1 <= args.operations <= 60 or any(not 1 <= step <= min(args.operations, 8) for step in args.workers):
        parser.error("Use até 60 operações por etapa e até 8 concorrentes na instância isolada.")
    if args.ollama_model and (args.operations > 12 or max(args.workers) > 4):
        parser.error("No modo Ollama, use até 12 operações por etapa e até 4 concorrentes.")
    output = args.output or Path("output/evaluation") / ("api_ollama_academic.json" if args.ollama_model else "api_academic.json")
    # The Rust Chroma client may keep file handles open until process exit on Windows.
    with TemporaryDirectory(prefix="ai-up-bench-", ignore_cleanup_errors=True) as temporary:
        results = run(Path(temporary).resolve(), sorted(set(args.workers)), args.operations, args.ollama_model)
    report = {"generated_at": datetime.now(UTC).isoformat(), "platform": platform.platform(),
              "python": platform.python_version(), "database": "temporary_sqlite", "embedding": "hash",
              "llm": args.ollama_model or "mock", "http": "loopback, one Uvicorn worker, synchronous index",
              "generation_workers": 2 if args.ollama_model else None, "results": results}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Relatório: {output}")


if __name__ == "__main__":
    main()
