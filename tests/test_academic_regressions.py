from contextlib import contextmanager
from uuid import uuid4

import httpx
import pytest
from sqlalchemy.exc import OperationalError

from app.db.session import SessionLocal, get_db
from app.models.document import Document, DocumentStatus
from app.models.generation import Generation
from app.services import generation_service
from app.services.generation_guard import GenerationGuard
from app.services.llm.base import LLMUnavailableError
from app.services.llm.ollama_provider import OllamaLLMProvider
from app.services.vector_store_service import RetrievedChunk, VectorStoreService
from tests.conftest import auth_headers
from tests.test_evolution import chat, upload
from tests.test_organizations import create_external_user


@pytest.mark.parametrize("visibility", ["ORGANIZATION", "TEAM"])
def test_revocation_blocks_history_search_export_and_replay(client, monkeypatch, visibility):
    owner = auth_headers(client, "outro@aiup.local")
    member = auth_headers(client)
    data = {"visibility": visibility}
    if visibility == "TEAM":
        admin = auth_headers(client, "admin@aiup.local")
        team_id = client.post("/api/organizations/teams", headers=admin, json={"name": "Pesquisa"}).json()["id"]
        member_id = client.get("/api/auth/me", headers=member).json()["id"]
        owner_id = client.get("/api/auth/me", headers=owner).json()["id"]
        membership = f"/api/organizations/teams/{team_id}/members"
        assert client.put(membership, headers=admin, json={"user_ids": [member_id, owner_id]}).status_code == 200
        data["team_id"] = str(team_id)
    marker = "SEGREDO-SINTETICO-745"
    document = client.post("/api/documents", headers=owner, data=data,
                           files={"file": ("contrato.txt", f"O prazo do contrato é 45 dias. Código {marker}.".encode(), "text/plain")})
    assert document.status_code == 201
    did = document.json()["id"]
    cid = chat(client, member, [did])
    base = f"/api/chats/{cid}"
    payload = {"message": "Qual o prazo do contrato?", "request_id": str(uuid4())}
    seen = []

    class Provider:
        def generate(self, question, context, history, instruction):
            seen.extend(item.content for item in history)
            return f"{marker} [1]." if any(marker in chunk.text for chunk in context) else "Outro prazo [1]."

    monkeypatch.setattr("app.services.rag_service.get_llm_provider", lambda _: Provider())
    monkeypatch.setattr(generation_service, "submit", lambda key: generation_service.run(key, generation_service.RunningGeneration()))
    assert client.post(f"{base}/generations", headers=member, json=payload).status_code == 202
    job = f"{base}/generations/{payload['request_id']}"
    assert marker in client.get(job, headers=member).text
    assert client.get("/api/chats", params={"q": marker}, headers=member).json()
    _, email = create_external_user()
    external = auth_headers(client, email)
    assert client.get(base, headers=external).status_code == 404
    assert client.get(f"{base}/export", headers=external).status_code == 404
    assert client.get(job, headers=external).status_code == 404
    assert client.post("/api/chats", headers=external, json={"document_ids": [did]}).status_code == 404
    if visibility == "TEAM":
        assert client.put(membership, headers=admin, json={"user_ids": [owner_id]}).status_code == 200
    else:
        assert client.patch(f"/api/documents/{did}", headers=owner, json={"visibility": "PRIVATE"}).status_code == 200

    for route in [base, job, f"{job}/events", *(f"{base}/export?format={fmt}" for fmt in ("json", "html", "markdown"))]:
        response = client.get(route, headers=member)
        assert response.status_code == 200
        assert marker not in response.text and "contrato.txt" not in response.text
    assert marker not in client.post(f"{base}/generations", headers=member, json=payload).text
    assert client.get("/api/chats", params={"q": marker}, headers=member).json() == []
    other_doc = upload(client, member, "manual.txt", "O prazo para entrega de contrato é 99 dias.")
    assert client.patch(base, headers=member, json={"document_ids": [other_doc["id"]]}).status_code == 200
    assert client.post(f"{base}/messages", headers=member, json={"message": "E qual é o prazo?"}).status_code == 200
    assert not any(marker in item for item in seen)
    assert client.delete(f"/api/documents/{did}", headers=owner).status_code == 204
    assert marker not in client.get(job, headers=member).text
    assert marker not in client.get(base, headers=member).text


@pytest.mark.parametrize(("status", "body", "error"), [
    (404, '{"error":"not found"}', "Modelo local"),
    (200, '{"message":{"content":"parcial"},"done":false}\n', "antes de concluí"),
    (200, '{"error":"model failure"}\n', "não conseguiu concluir"),
    (200, '[]\n', "interrompida"),
    (None, None, "interrompida"),
])
def test_ollama_failure_modes_never_complete(monkeypatch, status, body, error):
    @contextmanager
    def stream(method, url, **kwargs):
        assert kwargs["trust_env"] is False
        request = httpx.Request(method, url)
        if status is None:
            raise httpx.ConnectError("offline", request=request)
        yield httpx.Response(status, text=body, request=request)

    monkeypatch.setattr(httpx, "stream", stream)
    context = [RetrievedChunk("one", "Prazo de 30 dias.", 1, "manual.txt", None, 1)]
    with pytest.raises(LLMUnavailableError, match=error):
        list(OllamaLLMProvider("http://localhost:11434", "synthetic").generate_stream("Qual o prazo?", context))


def test_worker_failure_discards_partial_answer(client, monkeypatch):
    headers = auth_headers(client)
    doc = upload(client, headers)
    cid = chat(client, headers, [doc["id"]])
    key = str(uuid4())

    class Provider:
        def generate_stream(self, *args):
            yield "PARCIAL-SINTETICO"
            raise LLMUnavailableError("Modelo temporariamente indisponível.")

    monkeypatch.setattr("app.services.rag_service.get_llm_provider", lambda _: Provider())
    monkeypatch.setattr(generation_service, "submit", lambda job: generation_service.run(job, generation_service.RunningGeneration()))
    base = f"/api/chats/{cid}"
    assert client.post(f"{base}/generations", headers=headers, json={"message": "Qual o prazo de reembolso?", "request_id": key}).status_code == 202
    job = client.get(f"{base}/generations/{key}", headers=headers).json()
    assert job["status"] == "error" and job["result"] is None and "indisponível" in job["error"]
    assert client.get(base, headers=headers).json()["messages"] == []


def test_revocation_while_model_runs_prevents_persistence(client, monkeypatch):
    owner = auth_headers(client, "outro@aiup.local")
    member = auth_headers(client)
    response = client.post("/api/documents", headers=owner, data={"visibility": "ORGANIZATION"},
                           files={"file": ("acordo.txt", b"O prazo de entrega e 45 dias corridos.", "text/plain")})
    assert response.status_code == 201
    did = response.json()["id"]
    cid = chat(client, member, [did])

    class Provider:
        def generate(self, question, context, *args):
            assert [chunk.document_id for chunk in context] == [did]
            with SessionLocal() as db:
                from app.models.document import DocumentVisibility
                db.get(Document, did).visibility = DocumentVisibility.PRIVATE
                db.commit()
            return "O prazo é 45 dias [1]."

    monkeypatch.setattr("app.services.rag_service.get_llm_provider", lambda _: Provider())
    base = f"/api/chats/{cid}"
    result = client.post(f"{base}/messages", headers=member, json={"message": "Qual o prazo de entrega?"})
    assert result.status_code == 503 and "acesso a uma fonte mudou" in result.text
    assert client.get(base, headers=member).json()["messages"] == []


def test_restart_recovers_pending_work(client):
    from app.main import lifespan, app
    import asyncio

    headers = auth_headers(client)
    doc = upload(client, headers)
    cid = chat(client, headers)
    key = str(uuid4())
    with SessionLocal() as db:
        item = db.get(Document, doc["id"])
        index = item.index_generation
        item.status = DocumentStatus.PROCESSING
        db.add(Generation(id=key, chat_id=cid, user_id=item.user_id, question="Pergunta pendente", status="running", stage="Testando"))
        db.commit()

    async def restart():
        async with lifespan(app):
            pass

    asyncio.run(restart())
    with SessionLocal() as db:
        item = db.get(Document, doc["id"])
        assert item.status == DocumentStatus.READY and item.index_generation == index
        assert db.get(Generation, key).status == "error"


def test_database_outage_returns_degraded(client):
    class Offline:
        def execute(self, *args):
            raise OperationalError(None, None, RuntimeError("credencial fictícia"))

    client.app.dependency_overrides[get_db] = Offline
    try:
        response = client.get("/api/health")
        assert response.json() == {"status": "degraded", "database": "unavailable"}
        assert "credencial" not in response.text
    finally:
        del client.app.dependency_overrides[get_db]


def test_invalid_pdf_and_failed_first_index(client, monkeypatch):
    headers = auth_headers(client)
    invalid = client.post("/api/documents", headers=headers, files={"file": ("invalid.pdf", b"not a PDF", "application/pdf")})
    assert 400 <= invalid.status_code < 500

    def failed_write(*args, **kwargs):
        raise OSError("Index unavailable")

    monkeypatch.setattr(VectorStoreService, "add_document", failed_write)
    document = upload(client, headers)
    with SessionLocal() as db:
        item = db.get(Document, document["id"])
        assert item.status == DocumentStatus.ERROR and item.index_generation is None
        assert "preparar a busca" in item.error_message


def test_literal_guard_checks_the_cited_chunk_only():
    chunks = [RetrievedChunk("a", "A taxa é 15%.", 1, "manual.txt", None, 1, citation=1),
              RetrievedChunk("b", "A taxa é 5%.", 2, "anexo.txt", None, 1, citation=2)]
    assert GenerationGuard.has_unsupported_literal("A taxa é 5% [1].", chunks)
    assert not GenerationGuard.has_unsupported_literal("A taxa é 5% [2].", chunks)


@pytest.mark.parametrize("model", ["gemma4:cloud", "qwen3:32b-cloud", "gemma4:CLOUD"])
def test_loopback_address_does_not_allow_cloud_model(model):
    from pydantic import ValidationError
    from app.core.config import Settings

    with pytest.raises(ValidationError, match="encaminhamento para a nuvem"):
        Settings(_env_file=None, llm_provider="ollama", ollama_model=model)


def test_fabricated_citation_is_not_saved_as_an_evidence_reference(client, monkeypatch):
    headers = auth_headers(client)
    doc = upload(client, headers)
    cid = chat(client, headers, [doc["id"]])

    class Provider:
        def generate(self, *args):
            return "O prazo de reembolso é 30 dias [1]. Um documento falso afirma outra coisa [999] [N]."

    monkeypatch.setattr("app.services.rag_service.get_llm_provider", lambda _: Provider())
    result = client.post(f"/api/chats/{cid}/messages", headers=headers, json={"message": "Qual o prazo de reembolso?"})
    assert result.status_code == 200
    answer = result.json()
    assert "[1]" in answer["answer"] and "[999]" not in answer["answer"] and "[N]" not in answer["answer"]
    assert answer["metrics"]["citation_warning"] and [item["citation"] for item in answer["sources"]] == [1]


def test_reprocessing_write_failure_keeps_active_generation(client, monkeypatch):
    from app.core.config import get_settings
    from app.services.document_service import DocumentService

    headers = auth_headers(client)
    doc = upload(client, headers)
    original_write = VectorStoreService.add_document

    def partial_write(*args, **kwargs):
        original_write(*args, **kwargs)
        raise OSError("synthetic post-write failure")

    monkeypatch.setattr(VectorStoreService, "add_document", partial_write)
    with SessionLocal() as db:
        item = db.get(Document, doc["id"])
        previous = item.index_generation
        DocumentService(get_settings()).process(db, item)
        assert item.status == DocumentStatus.READY and item.index_generation == previous
        index = VectorStoreService(get_settings().resolved_chroma_dir)
        chunks = index.collection.get(where={"document_id": item.id}, include=["metadatas"])
        assert {meta["generation"] for meta in chunks["metadatas"]} == {previous}
