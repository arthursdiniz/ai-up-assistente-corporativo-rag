from fastapi.testclient import TestClient

from tests.conftest import PASSWORD, auth_headers


def test_valid_login(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login", json={"email": "usuario@aiup.local", "password": PASSWORD}
    )
    assert response.status_code == 200
    assert response.json()["user"]["role"] == "USER"
    assert response.json()["access_token"]


def test_invalid_login(client: TestClient) -> None:
    response = client.post(
        "/api/auth/login", json={"email": "usuario@aiup.local", "password": "incorreta"}
    )
    assert response.status_code == 401


def test_protected_route_without_token(client: TestClient) -> None:
    response = client.get("/api/auth/me")
    assert response.status_code == 401


def test_current_user(client: TestClient) -> None:
    response = client.get("/api/auth/me", headers=auth_headers(client))
    assert response.status_code == 200
    assert response.json()["email"] == "usuario@aiup.local"
