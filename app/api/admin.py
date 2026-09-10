from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.permissions import require_roles
from app.core.config import get_settings
from app.db.session import get_db
from app.models.audit_log import AuditLog
from app.models.chat import Chat
from app.models.document import Document, DocumentStatus
from app.models.message import Message, MessageRole
from app.models.user import User, UserRole
from app.schemas.admin import AdminStats, AuditLogPage, TechnicalInfo


router = APIRouter(prefix="/admin", tags=["Administração"])
administrative = require_roles(UserRole.MANAGER, UserRole.IT_ADMIN)
it_admin_only = require_roles(UserRole.IT_ADMIN)


@router.get("/logs", response_model=AuditLogPage)
def list_logs(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(administrative),
    db: Session = Depends(get_db),
) -> AuditLogPage:
    total = db.scalar(
        select(func.count(AuditLog.id)).where(
            AuditLog.organization_id == current_user.organization_id
        )
    ) or 0
    items = list(
        db.scalars(
            select(AuditLog)
            .where(AuditLog.organization_id == current_user.organization_id)
            .order_by(AuditLog.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return AuditLogPage(items=items, total=total, page=page, page_size=page_size)


@router.get("/stats", response_model=AdminStats)
def stats(current_user: User = Depends(administrative), db: Session = Depends(get_db)) -> AdminStats:
    organization_id = current_user.organization_id
    return AdminStats(
        users=db.scalar(select(func.count(User.id)).where(User.organization_id == organization_id)) or 0,
        documents=db.scalar(select(func.count(Document.id)).where(Document.organization_id == organization_id)) or 0,
        documents_ready=db.scalar(
            select(func.count(Document.id)).where(
                Document.organization_id == organization_id,
                Document.status == DocumentStatus.READY,
            )
        ) or 0,
        documents_error=db.scalar(
            select(func.count(Document.id)).where(
                Document.organization_id == organization_id,
                Document.status == DocumentStatus.ERROR,
            )
        ) or 0,
        chats=db.scalar(
            select(func.count(Chat.id)).join(User).where(User.organization_id == organization_id)
        ) or 0,
        messages=db.scalar(
            select(func.count(Message.id))
            .join(Chat)
            .join(User)
            .where(User.organization_id == organization_id)
        ) or 0,
        ai_questions=db.scalar(
            select(func.count(Message.id))
            .join(Chat)
            .join(User)
            .where(
                User.organization_id == organization_id,
                Message.role == MessageRole.USER,
            )
        ) or 0,
    )


@router.get("/technical", response_model=TechnicalInfo)
def technical_info(_: User = Depends(it_admin_only)) -> TechnicalInfo:
    settings = get_settings()
    return TechnicalInfo(
        environment=settings.app_env,
        database_backend=settings.database_url.split(":", maxsplit=1)[0],
        llm_provider=settings.llm_provider,
        llm_model=settings.ollama_model if settings.llm_provider == "ollama" else "mock",
        embedding_provider=settings.embedding_provider,
        embedding_model=settings.embedding_model,
        chroma_persistence=True,
    )


@router.get("/quality")
def quality(current_user: User = Depends(administrative), db: Session = Depends(get_db)):
    messages = list(db.scalars(
        select(Message)
        .join(Chat)
        .join(User)
        .where(
            User.organization_id == current_user.organization_id,
            Message.role == MessageRole.ASSISTANT,
        )
        .order_by(Message.id.desc())
        .limit(500)
    ))
    timed = [item.metrics["total_ms"] for item in messages if item.metrics and "total_ms" in item.metrics]
    return {"sample_size":len(messages), "positive":sum(item.feedback == 1 for item in messages),
        "negative":sum(item.feedback == -1 for item in messages),
        "insufficient":sum((item.metrics or {}).get("status") == "insufficient" for item in messages),
        "average_seconds":round(sum(timed)/len(timed)/1000, 1) if timed else None,
        "recent_feedback":[{"message_id":item.id, "reason":item.feedback_reason or "Sem motivo informado"} for item in messages if item.feedback == -1][:20]}
