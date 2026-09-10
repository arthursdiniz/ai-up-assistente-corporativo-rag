import asyncio
from html import escape
import json
from uuid import UUID, uuid4
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import select, func, or_
from sqlalchemy.orm import Session, selectinload

from app.core.permissions import get_current_user
from app.core.config import get_settings
from app.db.session import get_db, SessionLocal
from app.models.chat import Chat
from app.models.document import Document
from app.models.generation import Generation
from app.models.message import Message, MessageRole
from app.models.message_source import MessageSource
from app.models.user import User
from app.repositories.chat_repository import ChatRepository
from app.schemas.chat import (AskRequest, AskResponse, ChatCreate, ChatRead, ChatSummary, ChatUpdate,
    FeedbackRead, FeedbackUpdate, MessageRead, SourceRead)
from app.services.rag_service import RAGService
from app.services.llm.base import LLMUnavailableError
from app.services.audit_service import AuditService
from app.services import generation_service

router = APIRouter(prefix="/chats", tags=["Conversas"])
repository = ChatRepository()
audit_service = AuditService()


def serialize_message(message):
    return MessageRead(id=message.id, role=message.role, content=message.content,
        created_at=message.created_at, feedback=message.feedback, feedback_reason=message.feedback_reason,
        metrics=message.metrics, sources=[SourceRead(document_id=source.document_id,
            document=source.document_name or (source.document.original_filename if source.document else "Documento removido"),
            page=source.page, sheet=source.sheet, excerpt=source.excerpt,
            location=source.location, citation=source.citation,
            relevance_score=source.relevance_score) for source in message.sources])


def owned(db, chat_id, user_id, *, lock=False):
    query = select(Chat).where(Chat.id == chat_id, Chat.user_id == user_id)
    if lock:
        query = query.with_for_update()
    chat = db.scalar(query)
    if not chat:
        raise HTTPException(404, "Conversa não encontrada.")
    return chat


def check_idle(db, chat_id):
    if db.scalar(select(Generation.id).where(Generation.chat_id == chat_id, Generation.status.in_(["queued","running"])).limit(1)):
        raise HTTPException(409, "Aguarde ou cancele a resposta em andamento.")


def validate_documents(db, user_id, ids):
    if ids is None:
        return
    found = set(db.scalars(select(Document.id).where(Document.user_id == user_id, Document.id.in_(ids))))
    if found != set(ids):
        raise HTTPException(404, "Um dos documentos selecionados não está disponível.")


@router.post("", response_model=ChatSummary, status_code=201)
def create_chat(payload: ChatCreate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if not payload.title.strip():
        raise HTTPException(422, "Informe um título.")
    validate_documents(db, current_user.id, payload.document_ids)
    chat = Chat(user_id=current_user.id, title=payload.title.strip(), document_ids=payload.document_ids)
    db.add(chat)
    db.flush()
    audit_service.record(db, "CREATE_CHAT", current_user.id, "chat", str(chat.id))
    db.commit()
    return chat


@router.get("", response_model=list[ChatSummary])
def list_chats(current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
               q: str = Query("", max_length=200), offset: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=200)):
    query = select(Chat).where(Chat.user_id == current_user.id)
    if q.strip():
        matches = select(Message.id).where(Message.chat_id == Chat.id, Message.content.icontains(q.strip(), autoescape=True)).exists()
        query = query.where(or_(Chat.title.icontains(q.strip(), autoescape=True), matches))
    return list(db.scalars(query.order_by(Chat.pinned.desc(), Chat.updated_at.desc(), Chat.id.desc()).offset(offset).limit(limit)))


@router.get("/{chat_id}", response_model=ChatRead)
def get_chat(chat_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db),
             offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=300)):
    chat = owned(db, chat_id, current_user.id)
    total = db.scalar(select(func.count(Message.id)).where(Message.chat_id == chat.id)) or 0
    messages = list(db.scalars(select(Message).where(Message.chat_id == chat.id)
        .options(selectinload(Message.sources).selectinload(MessageSource.document))
        .order_by(Message.created_at.desc(), Message.id.desc()).offset(offset).limit(limit)))
    return ChatRead(**ChatSummary.model_validate(chat).model_dump(), total_messages=total,
                    messages=[serialize_message(message) for message in reversed(messages)])


@router.patch("/{chat_id}", response_model=ChatSummary)
def update_chat(chat_id: int, payload: ChatUpdate, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    chat = owned(db, chat_id, current_user.id, lock=True)
    if "document_ids" in payload.model_fields_set:
        check_idle(db, chat.id)
        validate_documents(db, current_user.id, payload.document_ids)
        chat.document_ids = payload.document_ids
    if payload.title is not None:
        if not payload.title.strip():
            raise HTTPException(422, "Informe um título.")
        chat.title = payload.title.strip()
    if payload.pinned is not None:
        chat.pinned = payload.pinned
    audit_service.record(db, "UPDATE_CHAT", current_user.id, "chat", str(chat.id))
    db.commit()
    return chat


@router.delete("/{chat_id}", status_code=204)
def delete_chat(chat_id: int, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    chat = owned(db, chat_id, current_user.id, lock=True)
    check_idle(db, chat.id)
    audit_service.record(db, "DELETE_CHAT", current_user.id, "chat", str(chat.id))
    db.delete(chat)
    db.commit()
    return Response(status_code=204)


@router.post("/{chat_id}/messages", response_model=AskResponse)
def ask_ai(chat_id: int, payload: AskRequest, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    chat = owned(db, chat_id, current_user.id)
    check_idle(db, chat.id)
    try:
        return RAGService(get_settings()).ask(db, chat, current_user, payload.message)
    except LLMUnavailableError as exc:
        db.rollback()
        raise HTTPException(503, str(exc)) from exc


@router.patch("/{chat_id}/messages/{message_id}/feedback", response_model=FeedbackRead)
def feedback(chat_id: int, message_id: int, payload: FeedbackUpdate,
             current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    owned(db, chat_id, current_user.id)
    message = db.scalar(select(Message).where(Message.id == message_id, Message.chat_id == chat_id))
    if not message:
        raise HTTPException(404, "Mensagem não encontrada.")
    if message.role != MessageRole.ASSISTANT:
        raise HTTPException(400, "Avalie uma resposta do AI-Up.")
    message.feedback, message.feedback_reason = payload.feedback, (payload.reason or "").strip() or None
    audit_service.record(db, "RATE_AI_RESPONSE", current_user.id, "message", str(message.id), details={"feedback":payload.feedback})
    db.commit()
    return FeedbackRead(message_id=message.id, feedback=payload.feedback)


class GenerationRequest(AskRequest):
    request_id: UUID = Field(default_factory=uuid4)
    retry_message_id: int | None = None


def serialize_job(job):
    return {"id":job.id, "status":job.status, "stage":job.stage, "question":job.question,
            "retry_message_id":job.retry_message_id, "result":job.result, "error":job.error}


@router.post("/{chat_id}/generations", status_code=202)
def create_generation(chat_id: int, payload: GenerationRequest, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    chat = owned(db, chat_id, user.id, lock=True)
    key = str(payload.request_id)
    previous = db.get(Generation, key)
    if previous:
        if previous.user_id != user.id or previous.chat_id != chat.id or previous.question != payload.message or previous.retry_message_id != payload.retry_message_id:
            raise HTTPException(409, "Identificador de solicitação já utilizado.")
        return serialize_job(previous)
    check_idle(db, chat.id)
    active = db.scalar(select(func.count(Generation.id)).where(Generation.user_id == user.id, Generation.status.in_(["queued","running"]))) or 0
    if active >= 3:
        raise HTTPException(429, "Há muitas respostas em andamento. Aguarde uma delas.")
    if payload.retry_message_id:
        last = db.scalar(select(Message).where(Message.chat_id == chat.id).order_by(Message.id.desc()).limit(1))
        question = db.scalar(select(Message).where(Message.chat_id == chat.id, Message.role == MessageRole.USER).order_by(Message.id.desc()).limit(1))
        if not last or last.id != payload.retry_message_id or last.role != MessageRole.ASSISTANT or not question or question.content != payload.message:
            raise HTTPException(409, "Apenas a última resposta pode ser refeita. Para explorar uma anterior, envie uma nova pergunta.")
    job = Generation(id=key, chat_id=chat.id, user_id=user.id, question=payload.message,
                     retry_message_id=payload.retry_message_id, status="queued", stage="Na fila")
    db.add(job)
    db.commit()
    generation_service.submit(key)
    return serialize_job(job)


@router.get("/{chat_id}/generations")
def active_generations(chat_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    owned(db, chat_id, user.id)
    return [serialize_job(job) for job in db.scalars(select(Generation).where(
        Generation.chat_id == chat_id, Generation.user_id == user.id,
        Generation.status.in_(["queued","running"])).order_by(Generation.created_at))]


def owned_job(db, chat_id, generation_id, user_id):
    job = db.scalar(select(Generation).where(Generation.id == generation_id,
        Generation.chat_id == chat_id, Generation.user_id == user_id))
    if not job:
        raise HTTPException(404, "Resposta não encontrada.")
    return job


@router.post("/{chat_id}/generations/{generation_id}/cancel")
def cancel_generation(chat_id: int, generation_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    job = owned_job(db, chat_id, generation_id, user.id)
    state = generation_service.get_state(generation_id)
    if state:
        with state.lock:
            if not state.committed and job.status in ("queued","running"):
                state.cancel.set()
                job.status, job.stage = "cancelled", "Cancelado"
                db.commit()
    elif job.status in ("queued","running"):
        job.status, job.stage = "cancelled", "Cancelado"
        db.commit()
    return serialize_job(job)


@router.get("/{chat_id}/generations/{generation_id}")
def get_generation(chat_id: int, generation_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return serialize_job(owned_job(db, chat_id, generation_id, user.id))


@router.get("/{chat_id}/generations/{generation_id}/events")
async def generation_events(chat_id: int, generation_id: str, request: Request,
                            user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    owned_job(db, chat_id, generation_id, user.id)
    user_id = user.id
    db.commit()
    async def events():
        offset, stage = 0, None
        while not await request.is_disconnected():
            # Short-lived session; no DB connection is held during streaming waits.
            with SessionLocal() as session:
                job = owned_job(session, chat_id, generation_id, user_id)
                snapshot = serialize_job(job)
            if snapshot["stage"] != stage:
                stage = snapshot["stage"]
                yield "data: " + json.dumps({"type":"stage","data":stage}, ensure_ascii=False) + "\n\n"
            state = generation_service.get_state(generation_id)
            if state:
                with state.lock:
                    text = state.text
                if len(text) > offset:
                    yield "data: " + json.dumps({"type":"delta","data":text[offset:]}, ensure_ascii=False) + "\n\n"
                    offset = len(text)
            if snapshot["status"] in ("done","error","cancelled"):
                yield "data: " + json.dumps({"type":snapshot["status"],"data":snapshot}, ensure_ascii=False) + "\n\n"
                break
            yield ": keepalive\n\n"
            await asyncio.sleep(0.25)
    return StreamingResponse(events(), media_type="text/event-stream", headers={"Cache-Control":"no-store","X-Accel-Buffering":"no"})


@router.get("/{chat_id}/export")
def export_chat(chat_id: int, format: str = Query("markdown", pattern="^(markdown|html|json)$"),
                user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    chat = owned(db, chat_id, user.id)
    messages = list(db.scalars(select(Message).where(Message.chat_id == chat.id)
        .options(selectinload(Message.sources).selectinload(MessageSource.document)).order_by(Message.created_at, Message.id)))
    serialized = [serialize_message(message) for message in messages]
    lines = [f"# {chat.title}", "", "Exportado do AI-Up. Confira as fontes antes de usar as informações.", ""]
    for message in serialized:
        lines.extend(["## " + ("Você" if message.role == MessageRole.USER else "AI-Up"), "", message.content, ""])
        for source in message.sources:
            location = f"página {source.page}" if source.page else (source.location or source.sheet or "documento")
            lines.extend([f"- [{source.citation or '-'}] {source.document} — {location}", f"  Evidência: {source.excerpt or 'Não registrada.'}"])
        lines.append("")
    content = "\n".join(lines)
    media, extension = "text/markdown", "md"
    if format == "json":
        content = json.dumps({"title":chat.title,"messages":[message.model_dump(mode="json") for message in serialized]}, ensure_ascii=False, indent=2)
        media, extension = "application/json", "json"
    elif format == "html":
        content = '<!doctype html><html lang="pt-BR"><meta charset="utf-8"><title>'+escape(chat.title)+'</title><style>body{font:16px/1.6 system-ui;max-width:900px;margin:40px auto;padding:24px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit}@media print{body{margin:0}}</style><pre>'+escape(content)+'</pre></html>'
        media, extension = "text/html", "html"
    return Response(content, media_type=media, headers={"Content-Disposition":f'attachment; filename="ai-up-conversa-{chat.id}.{extension}"', "Cache-Control":"no-store"})
