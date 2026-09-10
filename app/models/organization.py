from typing import TYPE_CHECKING

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.audit_log import AuditLog
    from app.models.document import Document
    from app.models.team import Team
    from app.models.user import User


class Organization(TimestampMixin, Base):
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)

    users: Mapped[list["User"]] = relationship(back_populates="organization")
    teams: Mapped[list["Team"]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )
    documents: Mapped[list["Document"]] = relationship(back_populates="organization")
    audit_logs: Mapped[list["AuditLog"]] = relationship(back_populates="organization")
