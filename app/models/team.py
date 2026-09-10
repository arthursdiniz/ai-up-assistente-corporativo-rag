from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, DateTime, ForeignKey, String, Table, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.document import Document
    from app.models.organization import Organization
    from app.models.user import User


team_members = Table(
    "team_members",
    Base.metadata,
    Column("team_id", ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True),
    Column("user_id", ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
)


class Team(TimestampMixin, Base):
    __tablename__ = "teams"
    __table_args__ = (UniqueConstraint("organization_id", "name"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(120), nullable=False)

    organization: Mapped["Organization"] = relationship(back_populates="teams")
    members: Mapped[list["User"]] = relationship(
        secondary=team_members, back_populates="teams", passive_deletes=True
    )
    documents: Mapped[list["Document"]] = relationship(back_populates="team")

    @property
    def member_ids(self) -> list[int]:
        return [member.id for member in self.members]
