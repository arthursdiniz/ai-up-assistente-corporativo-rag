from datetime import UTC, datetime, timedelta
from hashlib import sha256

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.audit_log import AuditLog
from app.models.document import Document, DocumentVisibility
from app.models.invitation import Invitation
from app.models.user import User
from app.services.session_service import SessionService
from tests.conftest import PASSWORD, auth_headers


def test_secure_invitation_creates_user_in_organization_and_teams(
    client: TestClient,
) -> None:
    admin_headers = auth_headers(client, "admin@aiup.local")
    assert client.post(
        "/api/organizations/invitations",
        headers=auth_headers(client),
        json={"email": "convidada@empresa.com"},
    ).status_code == 403
    team = client.post(
        "/api/organizations/teams",
        headers=admin_headers,
        json={"name": "Comercial"},
    ).json()
    created = client.post(
        "/api/organizations/invitations",
        headers=admin_headers,
        json={
            "email": "Convidada@Empresa.com",
            "role": "MANAGER",
            "team_ids": [team["id"]],
        },
    )
    assert created.status_code == 201
    body = created.json()
    token = body["accept_path"].split("#", 1)[1]
    assert body["invitation"]["email"] == "convidada@empresa.com"
    assert token not in str(body["invitation"])

    with SessionLocal() as db:
        stored = db.get(Invitation, body["invitation"]["id"])
        assert stored is not None
        assert stored.token_hash == sha256(token.encode()).hexdigest()
        assert token != stored.token_hash

    inspected = client.post(
        "/api/auth/invitations/inspect", json={"token": token}
    )
    assert inspected.status_code == 200
    assert inspected.json()["organization_name"] == "Empresa de Teste"
    accepted = client.post(
        "/api/auth/invitations/accept",
        json={"token": token, "name": "Pessoa Convidada", "password": "Convite@123"},
    )
    assert accepted.status_code == 201
    assert accepted.json()["user"]["role"] == "MANAGER"
    assert accepted.json()["user"]["team_ids"] == [team["id"]]
    assert accepted.cookies.get(SessionService.cookie_name)
    assert client.post(
        "/api/auth/invitations/accept",
        json={"token": token, "name": "Repetida", "password": "Convite@123"},
    ).status_code == 409
    assert client.post(
        "/api/auth/invitations/inspect", json={"token": token}
    ).status_code == 404

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == "convidada@empresa.com"))
        assert user is not None and user.organization.name == "Empresa de Teste"
        assert [item.name for item in user.teams] == ["Comercial"]
        assert db.scalar(
            select(AuditLog).where(AuditLog.action == "ACCEPT_INVITATION")
        )


def test_invitation_can_be_revoked_and_expired_links_are_rejected(
    client: TestClient,
) -> None:
    headers = auth_headers(client, "admin@aiup.local")
    created = client.post(
        "/api/organizations/invitations",
        headers=headers,
        json={"email": "revogada@empresa.com"},
    ).json()
    token = created["accept_path"].split("#", 1)[1]
    invitation_id = created["invitation"]["id"]
    assert client.delete(
        f"/api/organizations/invitations/{invitation_id}", headers=headers
    ).status_code == 204
    assert client.post(
        "/api/auth/invitations/inspect", json={"token": token}
    ).status_code == 404

    expired = client.post(
        "/api/organizations/invitations",
        headers=headers,
        json={"email": "expirada@empresa.com"},
    ).json()
    expired_token = expired["accept_path"].split("#", 1)[1]
    with SessionLocal() as db:
        invitation = db.get(Invitation, expired["invitation"]["id"])
        assert invitation is not None
        invitation.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        db.commit()
    assert client.post(
        "/api/auth/invitations/inspect", json={"token": expired_token}
    ).status_code == 404


def test_team_rename_and_delete_make_team_documents_private(client: TestClient) -> None:
    headers = auth_headers(client, "admin@aiup.local")
    users = client.get("/api/users", headers=headers).json()
    user_ids = {user["email"]: user["id"] for user in users}
    team = client.post(
        "/api/organizations/teams", headers=headers, json={"name": "Vendas"}
    ).json()
    assert client.put(
        f"/api/organizations/teams/{team['id']}/members",
        headers=headers,
        json={"user_ids": [user_ids["usuario@aiup.local"], user_ids["outro@aiup.local"]]},
    ).status_code == 200
    renamed = client.patch(
        f"/api/organizations/teams/{team['id']}",
        headers=headers,
        json={"name": "Novos Negócios"},
    )
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Novos Negócios"

    owner_headers = auth_headers(client, "outro@aiup.local")
    document = client.post(
        "/api/documents",
        headers=owner_headers,
        data={"visibility": "TEAM", "team_id": str(team["id"])},
        files={"file": ("pipeline.txt", b"Meta comercial trimestral.", "text/plain")},
    ).json()
    assert client.get(
        f"/api/documents/{document['id']}", headers=auth_headers(client)
    ).status_code == 200
    assert client.delete(
        f"/api/organizations/teams/{team['id']}", headers=headers
    ).status_code == 204
    assert client.get(
        f"/api/documents/{document['id']}", headers=auth_headers(client)
    ).status_code == 404
    with SessionLocal() as db:
        stored = db.get(Document, document["id"])
        assert stored is not None
        assert stored.visibility == DocumentVisibility.PRIVATE
        assert stored.team_id is None


def test_deactivation_transfers_documents_atomically(client: TestClient) -> None:
    source_headers = auth_headers(client, "outro@aiup.local")
    document = client.post(
        "/api/documents",
        headers=source_headers,
        files={"file": ("procedimento.txt", b"Procedimento interno transferivel.", "text/plain")},
    ).json()
    admin_headers = auth_headers(client, "admin@aiup.local")
    users = client.get("/api/users", headers=admin_headers).json()
    ids = {user["email"]: user["id"] for user in users}
    assert client.patch(
        f"/api/users/{ids['outro@aiup.local']}",
        headers=admin_headers,
        json={"active": False},
    ).status_code == 409
    deactivated = client.post(
        f"/api/users/{ids['outro@aiup.local']}/deactivate",
        headers=admin_headers,
        json={"transfer_document_owner_id": ids["usuario@aiup.local"]},
    )
    assert deactivated.status_code == 200
    assert deactivated.json()["active"] is False
    assert client.get(
        f"/api/documents/{document['id']}", headers=source_headers
    ).status_code == 401
    assert client.get(
        f"/api/documents/{document['id']}", headers=auth_headers(client)
    ).status_code == 200
    with SessionLocal() as db:
        stored = db.get(Document, document["id"])
        assert stored is not None and stored.user_id == ids["usuario@aiup.local"]
        events = list(
            db.scalars(
                select(AuditLog.action).where(
                    AuditLog.resource_id == str(ids["outro@aiup.local"])
                )
            )
        )
        assert "TRANSFER_DOCUMENTS" in events
        assert "USER_BLOCKED" in events
