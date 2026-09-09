from fastapi.testclient import TestClient
import pymupdf

from app.services.llm.base import ConversationMessage, NO_CONTEXT_ANSWER
from app.services.rag_service import RAGService
from app.services.vector_store_service import RetrievedChunk
from tests.conftest import auth_headers


def prepare_chat_and_document(client: TestClient) -> tuple[dict[str, str], int]:
    headers = auth_headers(client)
    chat_id = client.post("/api/chats", headers=headers, json={"title": "Férias"}).json()["id"]
    upload = client.post(
        "/api/documents",
        headers=headers,
        files={
            "file": (
                "regulamento.txt",
                b"O colaborador possui direito a trinta dias de ferias apos cada periodo aquisitivo.",
                "text/plain",
            )
        },
    )
    assert upload.status_code == 201
    assert upload.json()["status"] == "READY"
    return headers, chat_id


def test_rag_mock_recovers_source(client: TestClient) -> None:
    headers, chat_id = prepare_chat_and_document(client)
    response = client.post(
        f"/api/chats/{chat_id}/messages",
        headers=headers,
        json={"message": "Quantos dias de ferias o colaborador possui?"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["answer"].startswith("[MOCK]")
    assert body["sources"][0]["document"] == "regulamento.txt"
    assert "trinta dias" in body["sources"][0]["excerpt"]


def test_rag_reports_missing_information(client: TestClient) -> None:
    headers, chat_id = prepare_chat_and_document(client)
    response = client.post(
        f"/api/chats/{chat_id}/messages",
        headers=headers,
        json={"message": "Qual e a cotacao do iene japones?"},
    )
    assert response.status_code == 200
    assert response.json()["answer"] == NO_CONTEXT_ANSWER
    assert response.json()["sources"] == []


def test_rag_omits_near_match_sources_when_model_reports_missing_information(
    client: TestClient, monkeypatch
) -> None:
    class NoContextProvider:
        def generate(self, question, context, history=None, task_instruction=None):
            assert context
            return NO_CONTEXT_ANSWER

    monkeypatch.setattr(
        "app.services.rag_service.get_llm_provider", lambda settings: NoContextProvider()
    )
    headers, chat_id = prepare_chat_and_document(client)
    response = client.post(
        f"/api/chats/{chat_id}/messages",
        headers=headers,
        json={"message": "Quantos dias de ferias o colaborador possui?"},
    )
    assert response.status_code == 200
    assert response.json()["answer"] == NO_CONTEXT_ANSWER
    assert response.json()["sources"] == []


def test_pdf_source_preserves_page_number(client: TestClient) -> None:
    headers = auth_headers(client)
    chat_id = client.post("/api/chats", headers=headers, json={"title": "PDF"}).json()["id"]
    pdf = pymupdf.open()
    page = pdf.new_page()
    page.insert_text((72, 72), "O prazo contratual para entrega e de quarenta e cinco dias.")
    content = pdf.tobytes()
    pdf.close()
    uploaded = client.post(
        "/api/documents",
        headers=headers,
        files={"file": ("contrato.pdf", content, "application/pdf")},
    )
    assert uploaded.status_code == 201
    assert uploaded.json()["status"] == "READY"
    answer = client.post(
        f"/api/chats/{chat_id}/messages",
        headers=headers,
        json={"message": "Qual e o prazo contratual para entrega?"},
    )
    assert answer.status_code == 200
    assert answer.json()["sources"][0]["document"] == "contrato.pdf"
    assert answer.json()["sources"][0]["page"] == 1


def test_sources_prefer_page_that_supports_generated_answer() -> None:
    chunks = [
        RetrievedChunk("p1", "Politica anual de ferias.", 1, "manual.pdf", 1, 0.8),
        RetrievedChunk(
            "p2",
            "Incidentes de seguranca devem ser comunicados em ate 1 hora.",
            1,
            "manual.pdf",
            2,
            0.7,
        ),
    ]
    sources = RAGService._supporting_sources(
        chunks, "O incidente de segurança deve ser comunicado em até 1 hora."
    )
    assert [source.page for source in sources] == [2]


def test_follow_up_question_expands_retrieval_with_recent_context() -> None:
    history = [
        ConversationMessage("user", "Qual é o setor da empresa Nexora?"),
        ConversationMessage("assistant", "A Nexora atua com soluções digitais."),
    ]
    query = RAGService._build_retrieval_query("Qual é a missão dela?", history)
    assert "Qual é a missão dela?" in query
    assert "empresa Nexora" in query


def test_open_ended_pronoun_question_uses_conversation_context() -> None:
    history = [
        ConversationMessage("user", "Quais são os valores da Nexora?"),
        ConversationMessage("assistant", "A Nexora valoriza transparência."),
    ]
    question = "O que mais é importante saber sobre ela?"
    query = RAGService._build_retrieval_query(question, history)
    assert query != question
    assert "Nexora" in query


def test_open_ended_follow_up_without_pronoun_uses_context() -> None:
    history = [ConversationMessage("user", "Apresente a empresa Nexora.")]
    question = "Pode detalhar?"
    assert RAGService._build_retrieval_query(question, history) != question


def test_explicit_question_does_not_mix_unrelated_history() -> None:
    history = [ConversationMessage("user", "Fale sobre a empresa Nexora.")]
    question = "Qual é o prazo para solicitar férias?"
    assert RAGService._build_retrieval_query(question, history) == question


def test_rag_passes_previous_messages_to_provider(client: TestClient, monkeypatch) -> None:
    captured_histories = []

    class HistorySpyProvider:
        def generate(self, question, context, history=None, task_instruction=None):
            captured_histories.append(list(history or []))
            return "[MOCK] Resposta baseada no contexto." if context else NO_CONTEXT_ANSWER

    monkeypatch.setattr(
        "app.services.rag_service.get_llm_provider", lambda settings: HistorySpyProvider()
    )
    headers, chat_id = prepare_chat_and_document(client)
    first = client.post(
        f"/api/chats/{chat_id}/messages",
        headers=headers,
        json={"message": "Qual é a regra de férias?"},
    )
    second = client.post(
        f"/api/chats/{chat_id}/messages",
        headers=headers,
        json={"message": "E quantos dias ela concede?"},
    )
    assert first.status_code == 200
    assert second.status_code == 200
    assert captured_histories[0] == []
    assert [message.role for message in captured_histories[1]] == ["user", "assistant"]
    assert captured_histories[1][0].content == "Qual é a regra de férias?"


def test_new_chat_gets_a_useful_title_after_first_question(client: TestClient) -> None:
    headers, chat_id = prepare_chat_and_document(client)
    client.patch(
        f"/api/chats/{chat_id}", headers=headers, json={"title": "Nova conversa"}
    )
    response = client.post(
        f"/api/chats/{chat_id}/messages",
        headers=headers,
        json={"message": "Quais são as regras de férias?"},
    )
    assert response.status_code == 200
    chat = client.get(f"/api/chats/{chat_id}", headers=headers).json()
    assert chat["title"] == "Quais são as regras de férias"
