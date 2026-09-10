from datetime import UTC, datetime, timedelta
from hashlib import sha256
import secrets

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models.refresh_token import RefreshToken
from app.models.user import User


class SessionService:
    cookie_name = "ai_up_refresh"

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    @staticmethod
    def _digest(token: str) -> str:
        return sha256(token.encode("utf-8")).hexdigest()

    @staticmethod
    def _expired(expires_at: datetime) -> bool:
        now = datetime.now(UTC)
        if expires_at.tzinfo is None:
            now = now.replace(tzinfo=None)
        return expires_at <= now

    def issue(self, db: Session, user_id: int) -> str:
        raw_token = secrets.token_urlsafe(48)
        db.add(
            RefreshToken(
                user_id=user_id,
                token_hash=self._digest(raw_token),
                expires_at=datetime.now(UTC)
                + timedelta(days=self.settings.refresh_token_expire_days),
            )
        )
        return raw_token

    def rotate(self, db: Session, raw_token: str | None) -> tuple[User, str] | None:
        if not raw_token:
            return None
        token = db.scalar(
            select(RefreshToken)
            .where(RefreshToken.token_hash == self._digest(raw_token))
            .with_for_update()
        )
        if token is None or token.revoked_at is not None or self._expired(token.expires_at):
            return None
        user = db.get(User, token.user_id)
        token.revoked_at = datetime.now(UTC)
        if user is None or not user.active:
            return None
        return user, self.issue(db, user.id)

    def revoke_all(self, db: Session, user_id: int) -> None:
        db.execute(
            update(RefreshToken)
            .where(RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
        )
