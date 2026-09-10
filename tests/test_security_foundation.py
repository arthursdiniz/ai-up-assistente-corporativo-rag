import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.core.cors import configure_cors
from app.services.bootstrap_service import (
    BootstrapForbidden,
    BootstrapService,
    BootstrapUnavailable,
)


def test_cors_allows_only_configured_origin_with_credentials() -> None:
    cors_app = FastAPI()
    configure_cors(
        cors_app,
        Settings(_env_file=None, cors_allowed_origins=["https://app.empresa.com"]),
    )

    @cors_app.get("/resource")
    def resource() -> dict[str, bool]:
        return {"ok": True}

    with TestClient(cors_app) as test_client:
        allowed = test_client.options(
            "/resource",
            headers={
                "Origin": "https://app.empresa.com",
                "Access-Control-Request-Method": "GET",
                "Access-Control-Request-Headers": "Authorization",
            },
        )
        denied = test_client.options(
            "/resource",
            headers={
                "Origin": "https://maliciosa.example",
                "Access-Control-Request-Method": "GET",
            },
        )

    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "https://app.empresa.com"
    assert allowed.headers["access-control-allow-credentials"] == "true"
    assert denied.status_code == 400
    assert "access-control-allow-origin" not in denied.headers


def test_bootstrap_requires_token_outside_development() -> None:
    settings = Settings(
        _env_file=None,
        app_env="production",
        secret_key="production-secret-key-with-at-least-32-bytes",
        bootstrap_token=None,
    )
    service = BootstrapService(settings)
    assert service.is_available() is False
    with pytest.raises(BootstrapUnavailable):
        service.validate_access("127.0.0.1", None)


def test_bootstrap_token_is_compared_before_access() -> None:
    settings = Settings(
        _env_file=None,
        bootstrap_token="token-de-bootstrap-com-24-caracteres",
    )
    service = BootstrapService(settings)
    with pytest.raises(BootstrapForbidden):
        service.validate_access("203.0.113.10", "token-incorreto")
    service.validate_access("203.0.113.10", "token-de-bootstrap-com-24-caracteres")


def test_bootstrap_without_token_rejects_remote_host_in_development() -> None:
    service = BootstrapService(Settings(_env_file=None, bootstrap_token=None))
    with pytest.raises(BootstrapForbidden):
        service.validate_access("203.0.113.10", None)
    service.validate_access("127.0.0.1", None)
