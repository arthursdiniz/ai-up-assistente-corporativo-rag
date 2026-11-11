from datetime import date, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, JSON, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AuditorRun(Base):
    __tablename__ = "auditor_runs"
    __table_args__ = (UniqueConstraint("user_id", "fingerprint"), Index("ix_auditor_runs_user_status", "user_id", "status"))

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    attempt: Mapped[str] = mapped_column(String(36))
    scope: Mapped[dict] = mapped_column(JSON)
    configuration: Mapped[dict] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    stage: Mapped[str] = mapped_column(String(120), default="Na fila")
    progress: Mapped[int] = mapped_column(default=0)
    outcome: Mapped[str | None] = mapped_column(String(40))
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditorRuleSet(Base):
    __tablename__ = "auditor_rule_sets"
    __table_args__ = (UniqueConstraint("document_id", "generation", "extractor_version"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"))
    generation: Mapped[str] = mapped_column(String(64))
    extractor_version: Mapped[str] = mapped_column(String(40))
    rules: Mapped[list] = mapped_column(JSON)
    limited: Mapped[bool] = mapped_column(Boolean)


class AuditorAlert(Base):
    __tablename__ = "auditor_alerts"
    __table_args__ = (UniqueConstraint("user_id", "fingerprint"), Index("ix_auditor_alerts_user_state", "user_id", "state"))

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    organization_id: Mapped[int] = mapped_column(ForeignKey("organizations.id", ondelete="CASCADE"))
    run_id: Mapped[str | None] = mapped_column(ForeignKey("auditor_runs.id", ondelete="SET NULL"))
    left_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    right_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), index=True)
    left_generation: Mapped[str] = mapped_column(String(64))
    right_generation: Mapped[str] = mapped_column(String(64))
    fingerprint: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(40))
    valid_until: Mapped[date | None] = mapped_column()
    state: Mapped[str] = mapped_column(String(20), default="PENDING_REVIEW")
    subject: Mapped[str] = mapped_column(String(240))
    explanation: Mapped[str] = mapped_column(Text)
    evidence: Mapped[list] = mapped_column(JSON)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AuditorReview(Base):
    __tablename__ = "auditor_reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    alert_id: Mapped[int] = mapped_column(ForeignKey("auditor_alerts.id", ondelete="CASCADE"), index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    state: Mapped[str] = mapped_column(String(20))
    justification: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
