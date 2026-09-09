from sqlalchemy import select

from app.core.security import hash_password, verify_password
from app.db.session import SessionLocal
from app.models.user import User
from scripts.seed import DEVELOPMENT_PASSWORD, seed


def test_seed_restores_demonstration_password() -> None:
    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == "usuario@aiup.local"))
        assert user is not None
        user.password_hash = hash_password("senha-antiga")
        db.commit()

    seed()

    with SessionLocal() as db:
        user = db.scalar(select(User).where(User.email == "usuario@aiup.local"))
        assert user is not None
        assert verify_password(DEVELOPMENT_PASSWORD, user.password_hash)
