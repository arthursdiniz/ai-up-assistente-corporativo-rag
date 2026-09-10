import enum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.audit_log import AuditLog
    from app.models.chat import Chat
    from app.models.document import Document
    from app.models.refresh_token import RefreshToken
    from app.models.organization import Organization
    from app.models.team import Team


class UserRole(str, enum.Enum):
    USER = "USER"
    MANAGER = "MANAGER"
    IT_ADMIN = "IT_ADMIN"


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, name="user_role", native_enum=False), default=UserRole.USER, nullable=False
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    token_version: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="RESTRICT"), index=True
    )

    organization: Mapped["Organization"] = relationship(back_populates="users")
    teams: Mapped[list["Team"]] = relationship(
        secondary="team_members", back_populates="members", passive_deletes=True
    )
    chats: Mapped[list["Chat"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    documents: Mapped[list["Document"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    audit_logs: Mapped[list["AuditLog"]] = relationship(back_populates="user")
    refresh_tokens: Mapped[list["RefreshToken"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )

    @property
    def team_ids(self) -> list[int]:
        return [team.id for team in self.teams]
