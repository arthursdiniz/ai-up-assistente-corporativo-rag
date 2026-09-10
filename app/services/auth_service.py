from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.models.user import User
from app.repositories.user_repository import UserRepository


DUMMY_PASSWORD_HASH = hash_password("ai-up-dummy-password-for-timing-only")


class AuthService:
    def __init__(self) -> None:
        self.users = UserRepository()

    def authenticate(self, db: Session, email: str, password: str) -> User | None:
        user = self.users.get_by_email(db, email)
        if user is None:
            # Executa o mesmo algoritmo caro para reduzir enumeração por tempo.
            verify_password(password, DUMMY_PASSWORD_HASH)
            return None
        if not verify_password(password, user.password_hash) or not user.active:
            return None
        return user
