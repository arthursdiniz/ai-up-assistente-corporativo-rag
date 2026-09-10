from dataclasses import dataclass
import ipaddress
import secrets
from threading import Lock

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.security import hash_password
from app.models.user import User, UserRole
from app.models.organization import Organization
from app.services.audit_service import AuditService
from app.services.session_service import SessionService


class BootstrapAlreadyCompleted(Exception):
    pass


class BootstrapForbidden(Exception):
    pass


class BootstrapUnavailable(Exception):
    pass


@dataclass(frozen=True)
class BootstrapResult:
    user: User
    refresh_token: str


class BootstrapService:
    # Serializa threads do processo. O advisory lock abaixo cobre processos
    # concorrentes quando o banco utilizado é PostgreSQL.
    _creation_lock = Lock()
    _postgres_lock_id = 4_189_971_110

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.audit = AuditService()
        self.sessions = SessionService(settings)

    def is_required(self, db: Session) -> bool:
        return db.scalar(select(User.id).limit(1)) is None

    def is_available(self) -> bool:
        return bool(self.settings.bootstrap_token) or self.settings.app_env == "development"

    def token_required(self) -> bool:
        return bool(self.settings.bootstrap_token)

    def validate_access(self, client_host: str | None, provided_token: str | None) -> None:
        configured = self.settings.bootstrap_token
        if configured:
            expected = configured.get_secret_value()
            if not provided_token or not secrets.compare_digest(provided_token, expected):
                raise BootstrapForbidden
            return
        if self.settings.app_env != "development":
            raise BootstrapUnavailable
        host = (client_host or "").strip().strip("[]")
        if host == "testclient":
            return
        try:
            if ipaddress.ip_address(host).is_loopback:
                return
        except ValueError:
            pass
        raise BootstrapForbidden

    def create_first_admin(
        self,
        db: Session,
        *,
        name: str,
        email: str,
        password: str,
        ip_address: str | None,
    ) -> BootstrapResult:
        with self._creation_lock:
            try:
                if db.bind is not None and db.bind.dialect.name == "postgresql":
                    db.execute(
                        text("SELECT pg_advisory_xact_lock(:lock_id)"),
                        {"lock_id": self._postgres_lock_id},
                    )
                if not self.is_required(db):
                    raise BootstrapAlreadyCompleted
                organization = db.scalar(
                    select(Organization).order_by(Organization.id).limit(1)
                )
                if organization is None:
                    organization = Organization(name="Minha organização")
                    db.add(organization)
                    db.flush()
                user = User(
                    name=name,
                    email=email,
                    password_hash=hash_password(password),
                    role=UserRole.IT_ADMIN,
                    organization_id=organization.id,
                )
                db.add(user)
                db.flush()
                self.audit.record(
                    db,
                    "BOOTSTRAP_ADMIN",
                    user.id,
                    "user",
                    str(user.id),
                    ip_address=ip_address,
                )
                refresh_token = self.sessions.issue(db, user.id)
                db.commit()
                db.refresh(user)
                return BootstrapResult(user=user, refresh_token=refresh_token)
            except Exception:
                db.rollback()
                raise
