from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.user import User
from app.services.document_access_service import DocumentAccessService


class DocumentRepository:
    def __init__(self) -> None:
        self.access = DocumentAccessService()

    def get_owned(self, db: Session, document_id: int, user_id: int) -> Document | None:
        return db.scalar(
            select(Document).where(Document.id == document_id, Document.user_id == user_id)
        )

    def list_owned(self, db: Session, user_id: int) -> list[Document]:
        return list(
            db.scalars(
                select(Document)
                .where(Document.user_id == user_id)
                .order_by(Document.created_at.desc())
            )
        )

    def get_accessible(
        self, db: Session, document_id: int, user: User
    ) -> Document | None:
        return self.access.get_accessible(db, document_id, user)
