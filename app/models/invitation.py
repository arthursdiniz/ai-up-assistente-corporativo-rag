from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Column, DateTime, Enum, ForeignKey, String, Table, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin
from app.models.user import UserRole

if TYPE_CHECKING:
    from app.models.organization import Organization
    from app.models.team import Team
    from app.models.user import User


invitation_teams = Table(
    "invitation_teams",
    Base.metadata,
    Column(
        "invitation_id",
        ForeignKey("invitations.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column("team_id", ForeignKey("teams.id", ondelete="CASCADE"), primary_key=True),
)


class Invitation(TimestampMixin, Base):
    __tablename__ = "invitations"

    id: Mapped[int] = mapped_column(primary_key=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), index=True
    )
    created_by_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), index=True
    )
    email: Mapped[str] = mapped_column(String(320), index=True, nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", native_enum=False),
        default=UserRole.USER,
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    organization: Mapped["Organization"] = relationship(back_populates="invitations")
    created_by: Mapped["User | None"] = relationship(foreign_keys=[created_by_id])
    teams: Mapped[list["Team"]] = relationship(secondary=invitation_teams)

    @property
    def team_ids(self) -> list[int]:
        return [team.id for team in self.teams]
