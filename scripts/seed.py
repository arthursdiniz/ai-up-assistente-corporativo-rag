"""Create missing demonstration users; resetting existing accounts requires an explicit flag."""
from pathlib import Path
import os
import sys
import argparse

from sqlalchemy import select


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
from scripts._environment import load_user_environment
load_user_environment()

from app.core.security import hash_password  # noqa: E402
from app.db.session import SessionLocal  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402


DEVELOPMENT_PASSWORD = os.getenv("SEED_PASSWORD", "AiUp@2026")
DEMO_USERS = (
    ("Usuário AI-Up", "usuario@aiup.local", UserRole.USER),
    ("Gerente AI-Up", "gerente@aiup.local", UserRole.MANAGER),
    ("Administrador AI-Up", "admin@aiup.local", UserRole.IT_ADMIN),
)


def seed(reset_demo: bool = False) -> None:
    with SessionLocal() as db:
        for name, email, role in DEMO_USERS:
            user = db.scalar(select(User).where(User.email == email))
            if user is None:
                db.add(
                    User(
                        name=name,
                        email=email,
                        role=role,
                        active=True,
                        password_hash=hash_password(DEVELOPMENT_PASSWORD),
                    )
                )
            elif reset_demo:
                user.name = name
                user.role = role
                user.active = True
                user.password_hash = hash_password(DEVELOPMENT_PASSWORD)
                user.token_version += 1
        db.commit()
    print("Usuários de demonstração preparados. Contas existentes preservadas." if not reset_demo else "Contas de demonstração redefinidas explicitamente.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--reset-demo", action="store_true", help="Redefine explicitamente as três contas de demonstração")
    seed(parser.parse_args().reset_demo)
