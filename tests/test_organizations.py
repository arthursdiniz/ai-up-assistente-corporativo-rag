from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.organization import Organization
from app.models.user import User, UserRole
from tests.conftest import PASSWORD, auth_headers


def create_external_user() -> tuple[int, str]:
    with SessionLocal() as db:
        organization = Organization(name="Outra Empresa")
        db.add(organization)
        db.flush()
        user = User(
            name="Pessoa Externa",
            email="externa@outra.local",
            password_hash=hash_password(PASSWORD),
            role=UserRole.IT_ADMIN,
            organization_id=organization.id,
        )
        db.add(user)
        db.commit()
        return user.id, user.email


def test_organization_and_team_management_are_tenant_scoped(client: TestClient) -> None:
    admin_headers = auth_headers(client, "admin@aiup.local")
    user_headers = auth_headers(client)
    current = client.get("/api/organizations/current", headers=user_headers)
    assert current.status_code == 200
    assert current.json()["name"] == "Empresa de Teste"
    assert client.post(
        "/api/organizations/teams", headers=user_headers, json={"name": "Financeiro"}
    ).status_code == 403

    team = client.post(
        "/api/organizations/teams",
        headers=admin_headers,
        json={"name": "Financeiro"},
    )
    assert team.status_code == 201
    users = client.get("/api/users", headers=admin_headers).json()
    member_ids = [item["id"] for item in users if item["email"] != "gerente@aiup.local"]
    updated = client.put(
        f"/api/organizations/teams/{team.json()['id']}/members",
        headers=admin_headers,
        json={"user_ids": member_ids},
    )
    assert updated.status_code == 200
    assert set(updated.json()["member_ids"]) == set(member_ids)
    member_view = client.get("/api/organizations/current", headers=user_headers).json()
    assert [item["name"] for item in member_view["teams"]] == ["Financeiro"]
    assert member_view["teams"][0]["member_ids"] == []
    manager_view = client.get(
        "/api/organizations/current",
        headers=auth_headers(client, "gerente@aiup.local"),
    ).json()
    assert manager_view["teams"] == []

    external_id, external_email = create_external_user()
    assert client.put(
        f"/api/organizations/teams/{team.json()['id']}/members",
        headers=admin_headers,
        json={"user_ids": [external_id]},
    ).status_code == 404
    assert external_email not in {
        item["email"] for item in client.get("/api/users", headers=admin_headers).json()
    }
    assert client.patch(
        f"/api/users/{external_id}", headers=admin_headers, json={"active": False}
    ).status_code == 404


def test_organization_and_team_documents_respect_access_and_ownership(
    client: TestClient,
) -> None:
    admin_headers = auth_headers(client, "admin@aiup.local")
    owner_headers = auth_headers(client, "outro@aiup.local")
    member_headers = auth_headers(client, "usuario@aiup.local")
    manager_headers = auth_headers(client, "gerente@aiup.local")
    users = client.get("/api/users", headers=admin_headers).json()
    ids = {item["email"]: item["id"] for item in users}

    team = client.post(
        "/api/organizations/teams", headers=admin_headers, json={"name": "Jurídico"}
    ).json()
    assert client.put(
        f"/api/organizations/teams/{team['id']}/members",
        headers=admin_headers,
        json={"user_ids": [ids["usuario@aiup.local"], ids["outro@aiup.local"]]},
    ).status_code == 200

    organization_document = client.post(
        "/api/documents",
        headers=owner_headers,
        data={"visibility": "ORGANIZATION"},
        files={"file": ("politica-compartilhada.txt", b"O prazo corporativo e de 42 dias.", "text/plain")},
    )
    assert organization_document.status_code == 201
    organization_id = organization_document.json()["id"]
    shared = client.get(f"/api/documents/{organization_id}", headers=member_headers)
    assert shared.status_code == 200
    assert shared.json()["is_owner"] is False
    assert shared.json()["visibility"] == "ORGANIZATION"
    assert client.patch(
        f"/api/documents/{organization_id}",
        headers=member_headers,
        json={"category": "Alterada"},
    ).status_code == 404
    assert client.delete(
        f"/api/documents/{organization_id}", headers=member_headers
    ).status_code == 404

    team_document = client.post(
        "/api/documents",
        headers=owner_headers,
        data={"visibility": "TEAM", "team_id": str(team["id"])},
        files={"file": ("juridico.txt", b"A clausula interna exige duas aprovacoes.", "text/plain")},
    )
    assert team_document.status_code == 201
    team_document_id = team_document.json()["id"]
    assert client.get(f"/api/documents/{team_document_id}", headers=member_headers).status_code == 200
    assert client.get(f"/api/documents/{team_document_id}", headers=manager_headers).status_code == 404
    denied_share = client.post(
        "/api/documents",
        headers=manager_headers,
        data={"visibility": "TEAM", "team_id": str(team["id"])},
        files={"file": ("fora-da-equipe.txt", b"Conteudo privado do time.", "text/plain")},
    )
    assert denied_share.status_code == 422

    _, external_email = create_external_user()
    external_headers = auth_headers(client, external_email)
    assert client.get(f"/api/documents/{organization_id}", headers=external_headers).status_code == 404

    chat = client.post(
        "/api/chats", headers=member_headers, json={"document_ids": [organization_id]}
    )
    assert chat.status_code == 201
    answer = client.post(
        f"/api/chats/{chat.json()['id']}/messages",
        headers=member_headers,
        json={"message": "Qual é o prazo corporativo?"},
    )
    assert answer.status_code == 200
    assert answer.json()["sources"][0]["document_id"] == organization_id


def test_admin_metrics_do_not_cross_organizations(client: TestClient) -> None:
    admin_headers = auth_headers(client, "admin@aiup.local")
    create_external_user()
    stats = client.get("/api/admin/stats", headers=admin_headers)
    assert stats.status_code == 200
    assert stats.json()["users"] == 4
