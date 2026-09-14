from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.config import Settings
from app.core.security import hash_password
from app.models.invitation import Invitation
from app.models.team import Team
from app.models.user import User, UserRole
from app.services.audit_service import AuditService
from app.services.session_service import SessionService


class InvalidInvitation(ValueError):
    pass


@dataclass(frozen=True)
class AcceptedInvitation:
    user: User
    refresh_token: str


class InvitationService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.audit = AuditService()
        self.sessions = SessionService(settings)

    @staticmethod
    def digest(token: str) -> str:
        return sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def expired(invitation: Invitation) -> bool:
        now = datetime.now(UTC)
        if invitation.expires_at.tzinfo is None:
            now = now.replace(tzinfo=None)
        return invitation.expires_at <= now

    def status(self, invitation: Invitation) -> str:
        if invitation.accepted_at is not None:
            return "ACCEPTED"
        if invitation.revoked_at is not None:
            return "REVOKED"
        if self.expired(invitation):
            return "EXPIRED"
        return "PENDING"

    def create(
        self,
        db: Session,
        *,
        organization_id: int,
        created_by_id: int,
        email: str,
        role: UserRole,
        teams: list[Team],
    ) -> tuple[Invitation, str]:
        raw_token = secrets.token_urlsafe(48)
        invitation = Invitation(
            organization_id=organization_id,
            created_by_id=created_by_id,
            email=email,
            role=role,
            token_hash=self.digest(raw_token),
            expires_at=datetime.now(UTC)
            + timedelta(hours=self.settings.invitation_expire_hours),
            teams=teams,
        )
        db.add(invitation)
        db.flush()
        self.audit.record(
            db,
            "CREATE_INVITATION",
            created_by_id,
            "invitation",
            str(invitation.id),
            details={"role": role.value, "team_count": len(teams)},
        )
        return invitation, raw_token

    def get_by_token(
        self, db: Session, raw_token: str, *, lock: bool = False
    ) -> Invitation | None:
        query = (
            select(Invitation)
            .where(Invitation.token_hash == self.digest(raw_token))
            .options(
                selectinload(Invitation.organization),
                selectinload(Invitation.teams),
            )
        )
        if lock:
            query = query.with_for_update()
        return db.scalar(query)

    def require_pending(self, invitation: Invitation | None) -> Invitation:
        if invitation is None or self.status(invitation) != "PENDING":
            raise InvalidInvitation("Este convite é inválido, expirou ou já foi utilizado.")
        return invitation

    def accept(
        self,
        db: Session,
        *,
        raw_token: str,
        name: str,
        password: str,
        ip_address: str | None,
    ) -> AcceptedInvitation:
        invitation = self.require_pending(self.get_by_token(db, raw_token, lock=True))
        if db.scalar(select(User.id).where(User.email == invitation.email)) is not None:
            raise InvalidInvitation("Já existe uma conta com o e-mail deste convite.")
        user = User(
            name=name,
            email=invitation.email,
            password_hash=hash_password(password),
            role=invitation.role,
            organization_id=invitation.organization_id,
            teams=list(invitation.teams),
        )
        db.add(user)
        db.flush()
        invitation.accepted_at = datetime.now(UTC)
        self.audit.record(
            db,
            "ACCEPT_INVITATION",
            user.id,
            "invitation",
            str(invitation.id),
            details={"team_count": len(invitation.teams)},
            ip_address=ip_address,
        )
        return AcceptedInvitation(user=user, refresh_token=self.sessions.issue(db, user.id))
