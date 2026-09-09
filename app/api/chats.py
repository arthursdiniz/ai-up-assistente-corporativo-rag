from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.permissions import get_current_user
from app.db.session import get_db
from app.models.chat import Chat
from app.models.message import Message
from app.models.user import User
from app.repositories.chat_repository import ChatRepository
from app.schemas.chat import (
    AskRequest,
    AskResponse,
    ChatCreate,
    ChatRead,
    ChatSummary,
    ChatUpdate,
    FeedbackRead,
    FeedbackUpdate,
    MessageRead,
    SourceRead,
)
from app.services.rag_service import RAGService
from app.core.config import get_settings
from app.services.llm.base import LLMUnavailableError
from app.services.audit_service import AuditService


router = APIRouter(prefix="/chats", tags=["Conversas"])
repository = ChatRepository()
audit_service = AuditService()


def serialize_message(message: Message) -> MessageRead:
    return MessageRead(
        id=message.id,
        role=message.role,
        content=message.content,
        created_at=message.created_at,
        feedback=message.feedback,
        sources=[
            SourceRead(
                document_id=source.document_id,
                document=source.document.original_filename,
                page=source.page,
                sheet=source.sheet,
                excerpt=source.excerpt,
                relevance_score=source.relevance_score,
            )
            for source in message.sources
        ],
    )


@router.post("", response_model=ChatSummary, status_code=status.HTTP_201_CREATED)
def create_chat(
    payload: ChatCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Chat:
    chat = Chat(user_id=current_user.id, title=payload.title.strip())
    db.add(chat)
    db.flush()
    audit_service.record(db, "CREATE_CHAT", current_user.id, "chat", str(chat.id))
    db.commit()
    db.refresh(chat)
    return chat


@router.get("", response_model=list[ChatSummary])
def list_chats(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[Chat]:
    return repository.list_owned(db, current_user.id)


@router.get("/{chat_id}", response_model=ChatRead)
def get_chat(
    chat_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> ChatRead:
    chat = repository.get_owned(db, chat_id, current_user.id, with_messages=True)
    if chat is None:
        raise HTTPException(status_code=404, detail="Conversa não encontrada.")
    return ChatRead(
        id=chat.id,
        title=chat.title,
        created_at=chat.created_at,
        updated_at=chat.updated_at,
        messages=[serialize_message(message) for message in chat.messages],
    )


@router.patch("/{chat_id}", response_model=ChatSummary)
def update_chat(
    chat_id: int,
    payload: ChatUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Chat:
    chat = repository.get_owned(db, chat_id, current_user.id)
    if chat is None:
        raise HTTPException(status_code=404, detail="Conversa não encontrada.")
    chat.title = payload.title.strip()
    audit_service.record(db, "UPDATE_CHAT", current_user.id, "chat", str(chat.id))
    db.commit()
    db.refresh(chat)
    return chat


@router.delete("/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_chat(
    chat_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Response:
    chat = repository.get_owned(db, chat_id, current_user.id)
    if chat is None:
        raise HTTPException(status_code=404, detail="Conversa não encontrada.")
    audit_service.record(db, "DELETE_CHAT", current_user.id, "chat", str(chat.id))
    db.delete(chat)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/{chat_id}/messages", response_model=AskResponse)
def ask_ai(
    chat_id: int,
    payload: AskRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> AskResponse:
    chat = repository.get_owned(db, chat_id, current_user.id)
    if chat is None:
        raise HTTPException(status_code=404, detail="Conversa não encontrada.")
    try:
        return RAGService(get_settings()).ask(db, chat, current_user, payload.message)
    except LLMUnavailableError as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.patch(
    "/{chat_id}/messages/{message_id}/feedback", response_model=FeedbackRead
)
def update_message_feedback(
    chat_id: int,
    message_id: int,
    payload: FeedbackUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> FeedbackRead:
    message = db.scalar(
        select(Message)
        .join(Chat, Chat.id == Message.chat_id)
        .where(
            Message.id == message_id,
            Message.chat_id == chat_id,
            Chat.user_id == current_user.id,
        )
    )
    if message is None:
        raise HTTPException(status_code=404, detail="Mensagem não encontrada.")
    if message.role.value != "ASSISTANT":
        raise HTTPException(
            status_code=400,
            detail="O feedback só pode ser registrado em respostas do AI-Up.",
        )
    message.feedback = payload.feedback
    audit_service.record(
        db,
        "RATE_AI_RESPONSE",
        current_user.id,
        "message",
        str(message.id),
        details={"feedback": payload.feedback},
    )
    db.commit()
    return FeedbackRead(message_id=message.id, feedback=payload.feedback)
