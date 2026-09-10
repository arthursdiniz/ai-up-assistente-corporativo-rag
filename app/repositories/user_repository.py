from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User


class UserRepository:
    def get_by_email(self, db: Session, email: str) -> User | None:
        return db.scalar(select(User).where(User.email == email.lower()))

    def list(self, db: Session, organization_id: int) -> list[User]:
        return list(
            db.scalars(
                select(User)
                .where(User.organization_id == organization_id)
                .order_by(User.name)
            )
        )
