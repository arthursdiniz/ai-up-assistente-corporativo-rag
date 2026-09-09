from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.chat import Chat
from app.models.user import User
from tests.conftest import auth_headers


def test_create_and_list_chat(client: TestClient) -> None:
    headers = auth_headers(client)
    created = client.post("/api/chats", headers=headers, json={"title": "Recursos Humanos"})
    assert created.status_code == 201
    listed = client.get("/api/chats", headers=headers)
    assert listed.status_code == 200
    assert [chat["title"] for chat in listed.json()] == ["Recursos Humanos"]


def test_chat_history(client: TestClient) -> None:
    headers = auth_headers(client)
    chat_id = client.post("/api/chats", headers=headers, json={"title": "Histórico"}).json()["id"]
    response = client.get(f"/api/chats/{chat_id}", headers=headers)
    assert response.status_code == 200
    assert response.json()["messages"] == []


def test_cannot_access_another_users_chat(client: TestClient) -> None:
    with SessionLocal() as db:
        other = db.scalar(select(User).where(User.email == "outro@aiup.local"))
        chat = Chat(user_id=other.id, title="Privado")
        db.add(chat)
        db.commit()
        db.refresh(chat)
        chat_id = chat.id
    response = client.get(f"/api/chats/{chat_id}", headers=auth_headers(client))
    assert response.status_code == 404


def test_feedback_is_persisted_and_isolated_by_chat_owner(client: TestClient) -> None:
    headers = auth_headers(client)
    chat_id = client.post(
        "/api/chats", headers=headers, json={"title": "Feedback"}
    ).json()["id"]
    uploaded = client.post(
        "/api/documents",
        headers=headers,
        files={"file": ("politica.txt", b"O prazo oficial e de quinze dias.", "text/plain")},
    )
    assert uploaded.status_code == 201
    answer = client.post(
        f"/api/chats/{chat_id}/messages",
        headers=headers,
        json={"message": "Qual e o prazo oficial?"},
    )
    message_id = answer.json()["message_id"]

    rated = client.patch(
        f"/api/chats/{chat_id}/messages/{message_id}/feedback",
        headers=headers,
        json={"feedback": 1},
    )
    assert rated.status_code == 200
    assert rated.json() == {"message_id": message_id, "feedback": 1}
    history = client.get(f"/api/chats/{chat_id}", headers=headers).json()
    assert history["messages"][-1]["feedback"] == 1

    denied = client.patch(
        f"/api/chats/{chat_id}/messages/{message_id}/feedback",
        headers=auth_headers(client, "outro@aiup.local"),
        json={"feedback": -1},
    )
    assert denied.status_code == 404
