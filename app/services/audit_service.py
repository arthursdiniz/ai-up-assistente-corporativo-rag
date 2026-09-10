from hashlib import sha256
from typing import Any

from sqlalchemy.orm import Session

from app.models.audit_log import AuditLog


class AuditService:
    @staticmethod
    def identifier_fingerprint(identifier: str) -> str:
        """Correlaciona tentativas sem persistir o e-mail informado."""
        return sha256(identifier.strip().lower().encode("utf-8")).hexdigest()[:16]

    def record(
        self,
        db: Session,
        action: str,
        user_id: int | None = None,
        resource_type: str | None = None,
        resource_id: str | None = None,
        details: dict[str, Any] | None = None,
        ip_address: str | None = None,
    ) -> AuditLog:
        log = AuditLog(
            user_id=user_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            details=details,
            ip_address=ip_address,
        )
        db.add(log)
        return log

    def record_login_failure(
        self, db: Session, email: str, ip_address: str | None
    ) -> AuditLog:
        return self.record(
            db,
            "LOGIN_FAILED",
            details={"identifier_fingerprint": self.identifier_fingerprint(email)},
            ip_address=ip_address,
        )
