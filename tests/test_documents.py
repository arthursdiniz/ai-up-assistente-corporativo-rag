from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.config import get_settings
from app.db.session import SessionLocal
from app.models.document import Document, DocumentStatus
from app.models.user import User
from tests.conftest import auth_headers


def test_upload_allowed_txt(client: TestClient) -> None:
    response = client.post(
        "/api/documents",
        headers=auth_headers(client),
        files={"file": ("politica.txt", b"A politica interna concede trinta dias de ferias.", "text/plain")},
    )
    assert response.status_code == 201
    assert response.json()["status"] == "READY"


def test_reject_invalid_extension(client: TestClient) -> None:
    response = client.post(
        "/api/documents",
        headers=auth_headers(client),
        files={"file": ("programa.exe", b"MZ-invalid", "application/octet-stream")},
    )
    assert response.status_code == 400


def test_delete_document(client: TestClient) -> None:
    headers = auth_headers(client)
    uploaded = client.post(
        "/api/documents",
        headers=headers,
        files={"file": ("manual.txt", b"Conteudo do manual corporativo.", "text/plain")},
    )
    document_id = uploaded.json()["id"]
    response = client.delete(f"/api/documents/{document_id}", headers=headers)
    assert response.status_code == 204
    assert client.get("/api/documents", headers=headers).json() == []


def test_cannot_access_another_users_document(client: TestClient) -> None:
    with SessionLocal() as db:
        other = db.scalar(select(User).where(User.email == "outro@aiup.local"))
        document = Document(
            user_id=other.id,
            filename="private.txt",
            original_filename="private.txt",
            file_type="TXT",
            file_path=str(get_settings().resolved_upload_dir / "private.txt"),
            status=DocumentStatus.READY,
        )
        db.add(document)
        db.commit()
        db.refresh(document)
        document_id = document.id
    response = client.get(f"/api/documents/{document_id}", headers=auth_headers(client))
    assert response.status_code == 404


def test_suggestions_are_based_on_an_owned_document(client: TestClient) -> None:
    headers = auth_headers(client)
    uploaded = client.post(
        "/api/documents",
        headers=headers,
        files={
            "file": (
                "politica-ferias.txt",
                b"A politica concede trinta dias de ferias.",
                "text/plain",
            )
        },
    )
    document_id = uploaded.json()["id"]
    response = client.get(
        f"/api/documents/{document_id}/suggestions", headers=headers
    )
    assert response.status_code == 200
    assert all(
        "politica-ferias.txt" in suggestion
        for suggestion in response.json()["suggestions"]
    )
