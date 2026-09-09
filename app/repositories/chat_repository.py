from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.models.chat import Chat
from app.models.message import Message
from app.models.message_source import MessageSource


class ChatRepository:
    def get_owned(self, db: Session, chat_id: int, user_id: int, with_messages: bool = False) -> Chat | None:
        query = select(Chat).where(Chat.id == chat_id, Chat.user_id == user_id)
        if with_messages:
            query = query.options(
                selectinload(Chat.messages)
                .selectinload(Message.sources)
                .selectinload(MessageSource.document)
            )
        return db.scalar(query)

    def list_owned(self, db: Session, user_id: int) -> list[Chat]:
        return list(
            db.scalars(
                select(Chat).where(Chat.user_id == user_id).order_by(Chat.updated_at.desc())
            )
        )
