from collections.abc import Generator
from pathlib import Path
import os
import tempfile


TEST_ROOT = Path(tempfile.mkdtemp(prefix="ai-up-tests-"))
os.environ["DATABASE_URL"] = f"sqlite+pysqlite:///{(TEST_ROOT / 'test.db').as_posix()}"
os.environ["UPLOAD_DIR"] = str(TEST_ROOT / "uploads")
os.environ["CHROMA_DIR"] = str(TEST_ROOT / "chroma")
os.environ["EMBEDDING_PROVIDER"] = "hash"
os.environ["LLM_PROVIDER"] = "mock"
os.environ["RAG_MIN_RELEVANCE"] = "0.25"
os.environ["SECRET_KEY"] = "test-only-secret-key-with-at-least-32-bytes"

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import SessionLocal, engine
from app.main import app
from app.models.user import User, UserRole
from app.services.vector_store_service import _collection


PASSWORD = "Teste@123"
PASSWORD_HASH = hash_password(PASSWORD)


@pytest.fixture(autouse=True)
def clean_state() -> Generator[None, None, None]:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    collection = _collection(str(get_settings().resolved_chroma_dir))
    existing = collection.get()["ids"]
    if existing:
        collection.delete(ids=existing)
    upload_dir = get_settings().resolved_upload_dir
    upload_dir.mkdir(parents=True, exist_ok=True)
    for path in upload_dir.iterdir():
        if path.is_file():
            path.unlink()
    with SessionLocal() as db:
        db.add_all(
            [
                User(name="Usuário", email="usuario@aiup.local", password_hash=PASSWORD_HASH, role=UserRole.USER),
                User(name="Gerente", email="gerente@aiup.local", password_hash=PASSWORD_HASH, role=UserRole.MANAGER),
                User(name="Admin", email="admin@aiup.local", password_hash=PASSWORD_HASH, role=UserRole.IT_ADMIN),
                User(name="Outro", email="outro@aiup.local", password_hash=PASSWORD_HASH, role=UserRole.USER),
            ]
        )
        db.commit()
    yield


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    with TestClient(app) as test_client:
        yield test_client


def auth_headers(client: TestClient, email: str = "usuario@aiup.local") -> dict[str, str]:
    response = client.post("/api/auth/login", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['access_token']}"}
