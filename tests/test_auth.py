from hashlib import sha256

from fastapi.testclient import TestClient
from sqlalchemy import select

from tests.conftest import PASSWORD, auth_headers
from app.db.session import SessionLocal
from app.main import app
from app.models.audit_log import AuditLog
from app.models.refresh_token import RefreshToken
from app.models.user import User, UserRole
from app.services.audit_service import AuditService
from app.services.auth_service import AuthService
from app.services.session_service import SessionService


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
    with SessionLocal() as db:
        event = db.scalar(select(AuditLog).where(AuditLog.action == "LOGIN_FAILED"))
        assert event is not None
        assert event.user_id is None
        assert event.ip_address == "testclient"
        assert event.details == {
            "identifier_fingerprint": AuditService.identifier_fingerprint(
                "usuario@aiup.local"
            )
        }
        assert "usuario@aiup.local" not in str(event.details)


def test_unknown_email_still_runs_password_verification(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    def fake_verify(password: str, password_hash: str) -> bool:
        calls.append((password, password_hash))
        return False

    monkeypatch.setattr("app.services.auth_service.verify_password", fake_verify)
    with SessionLocal() as db:
        assert AuthService().authenticate(db, "nao-existe@aiup.local", "qualquer") is None
    assert len(calls) == 1


def test_protected_route_without_token(client: TestClient) -> None:
    response = client.get("/api/auth/me")
    assert response.status_code == 401


def test_current_user(client: TestClient) -> None:
    response = client.get("/api/auth/me", headers=auth_headers(client))
    assert response.status_code == 200
    assert response.json()["email"] == "usuario@aiup.local"


def test_refresh_token_is_httponly_hashed_and_rotated(client: TestClient) -> None:
    login = client.post(
        "/api/auth/login",
        json={"email": "usuario@aiup.local", "password": PASSWORD},
    )
    original = login.cookies.get(SessionService.cookie_name)
    assert original
    cookie = login.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie

    with SessionLocal() as db:
        stored = db.scalar(
            select(RefreshToken).where(
                RefreshToken.token_hash == sha256(original.encode()).hexdigest()
            )
        )
        assert stored is not None
        assert original != stored.token_hash

    refreshed = client.post("/api/auth/refresh")
    assert refreshed.status_code == 200
    rotated = refreshed.cookies.get(SessionService.cookie_name)
    assert rotated and rotated != original
    assert client.get(
        "/api/auth/me",
        headers={"Authorization": f"Bearer {refreshed.json()['access_token']}"},
    ).status_code == 200

    with TestClient(app) as replay_client:
        replay_client.cookies.set(
            SessionService.cookie_name, original, path="/api/auth"
        )
        assert replay_client.post("/api/auth/refresh").status_code == 401


def test_logout_revokes_refresh_session(client: TestClient) -> None:
    login = client.post(
        "/api/auth/login",
        json={"email": "usuario@aiup.local", "password": PASSWORD},
    )
    response = client.post(
        "/api/auth/logout",
        headers={"Authorization": f"Bearer {login.json()['access_token']}"},
    )
    assert response.status_code == 200
    assert "max-age=0" in response.headers["set-cookie"].lower()
    assert client.post("/api/auth/refresh").status_code == 401


def test_bootstrap_is_closed_after_users_exist(client: TestClient) -> None:
    state = client.get("/api/auth/bootstrap")
    assert state.status_code == 200
    assert state.json() == {
        "required": False,
        "available": True,
        "token_required": False,
    }
    response = client.post(
        "/api/auth/register",
        json={
            "name": "Intruso",
            "email": "intruso@empresa.com",
            "password": "SenhaForte@123",
        },
    )
    assert response.status_code == 409


def test_bootstrap_creates_only_first_administrator_and_starts_session(client: TestClient) -> None:
    with SessionLocal() as db:
        db.query(User).delete(synchronize_session=False)
        db.commit()

    assert client.get("/api/auth/bootstrap").json()["required"] is True
    created = client.post(
        "/api/auth/register",
        json={
            "name": "  Primeira Administradora  ",
            "email": "ADMIN@EMPRESA.COM",
            "password": "SenhaForte@123",
        },
    )
    assert created.status_code == 201
    assert created.json()["user"]["role"] == "IT_ADMIN"
    assert created.json()["user"]["email"] == "admin@empresa.com"
    assert created.cookies.get(SessionService.cookie_name)
    access_token = created.json()["access_token"]
    assert client.get(
        "/api/auth/me", headers={"Authorization": f"Bearer {access_token}"}
    ).status_code == 200

    with SessionLocal() as db:
        users = list(db.scalars(select(User)))
        assert len(users) == 1 and users[0].role == UserRole.IT_ADMIN
        assert db.scalar(select(AuditLog).where(AuditLog.action == "BOOTSTRAP_ADMIN"))

    repeated = client.post(
        "/api/auth/register",
        json={
            "name": "Segundo",
            "email": "segundo@empresa.com",
            "password": "SenhaForte@123",
        },
    )
    assert repeated.status_code == 409
