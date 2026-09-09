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
    _: User = Depends(administrative),
    db: Session = Depends(get_db),
) -> AuditLogPage:
    total = db.scalar(select(func.count(AuditLog.id))) or 0
    items = list(
        db.scalars(
            select(AuditLog)
            .order_by(AuditLog.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
    )
    return AuditLogPage(items=items, total=total, page=page, page_size=page_size)


@router.get("/stats", response_model=AdminStats)
def stats(_: User = Depends(administrative), db: Session = Depends(get_db)) -> AdminStats:
    count = lambda model_id: db.scalar(select(func.count(model_id))) or 0
    return AdminStats(
        users=count(User.id),
        documents=count(Document.id),
        documents_ready=db.scalar(
            select(func.count(Document.id)).where(Document.status == DocumentStatus.READY)
        ) or 0,
        documents_error=db.scalar(
            select(func.count(Document.id)).where(Document.status == DocumentStatus.ERROR)
        ) or 0,
        chats=count(Chat.id),
        messages=count(Message.id),
        ai_questions=db.scalar(
            select(func.count(Message.id)).where(Message.role == MessageRole.USER)
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
