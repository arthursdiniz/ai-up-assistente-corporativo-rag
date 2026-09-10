from fastapi.testclient import TestClient
from sqlalchemy import select

from tests.conftest import PASSWORD, auth_headers
from app.db.session import SessionLocal
from app.models.audit_log import AuditLog
from app.models.user import User


def test_user_cannot_access_admin(client: TestClient) -> None:
    response = client.get("/api/admin/stats", headers=auth_headers(client))
    assert response.status_code == 403


def test_manager_can_access_logs(client: TestClient) -> None:
    response = client.get(
        "/api/admin/logs", headers=auth_headers(client, "gerente@aiup.local")
    )
    assert response.status_code == 200
    assert "items" in response.json()


def test_it_admin_can_manage_users(client: TestClient) -> None:
    response = client.post(
        "/api/users",
        headers=auth_headers(client, "admin@aiup.local"),
        json={
            "name": "Nova Pessoa",
            "email": "nova@aiup.local",
            "password": PASSWORD,
            "role": "USER",
        },
    )
    assert response.status_code == 201
    assert response.json()["email"] == "nova@aiup.local"


def test_user_access_changes_create_specific_audit_events(client: TestClient) -> None:
    headers = auth_headers(client, "admin@aiup.local")
    with SessionLocal() as db:
        target = db.scalar(select(User).where(User.email == "outro@aiup.local"))
        assert target is not None
        target_id = target.id

    assert client.patch(
        f"/api/users/{target_id}", headers=headers, json={"active": False}
    ).status_code == 200
    assert client.patch(
        f"/api/users/{target_id}", headers=headers, json={"active": True}
    ).status_code == 200
    assert client.patch(
        f"/api/users/{target_id}", headers=headers, json={"role": "MANAGER"}
    ).status_code == 200

    with SessionLocal() as db:
        events = list(
            db.scalars(
                select(AuditLog)
                .where(AuditLog.resource_id == str(target_id))
                .order_by(AuditLog.id)
            )
        )
    assert [event.action for event in events] == [
        "USER_BLOCKED",
        "USER_UNBLOCKED",
        "USER_ROLE_CHANGED",
    ]
    assert events[-1].details == {"from": "USER", "to": "MANAGER"}
