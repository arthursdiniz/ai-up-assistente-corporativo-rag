from fastapi.testclient import TestClient

from tests.conftest import PASSWORD, auth_headers


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
