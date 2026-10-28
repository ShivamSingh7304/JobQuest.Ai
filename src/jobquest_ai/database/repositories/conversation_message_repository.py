from sqlalchemy import func, select
from sqlalchemy.orm import Session

from jobquest_ai.database.models.conversation_message import ConversationMessage


class ConversationMessageRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def _next_position(self, conversation_id: int) -> int:
        """Return the next sequential position index for a conversation."""
        result = self.db.scalar(
            select(func.max(ConversationMessage.position)).where(
                ConversationMessage.conversation_id == conversation_id
            )
        )
        return 0 if result is None else result + 1

    def add(
        self,
        conversation_id: int,
        role: str,
        content: str,
    ) -> ConversationMessage:
        """Append a single message to a conversation."""
        if role not in {"user", "assistant"}:
            raise ValueError(
                f"Invalid role '{role}'. Must be 'user' or 'assistant'."
            )
        if not content or not content.strip():
            raise ValueError("Message content must not be empty.")

        position = self._next_position(conversation_id)
        message = ConversationMessage(
            conversation_id=conversation_id,
            role=role,
            content=content.strip(),
            position=position,
        )
        self.db.add(message)
        self.db.commit()
        self.db.refresh(message)
        return message

    def list_by_conversation(
        self,
        conversation_id: int,
        skip: int = 0,
        limit: int = 100,
    ) -> list[ConversationMessage]:
        """Return messages ordered by position (oldest first)."""
        statement = (
            select(ConversationMessage)
            .where(
                ConversationMessage.conversation_id == conversation_id
            )
            .order_by(ConversationMessage.position)
            .offset(max(skip, 0))
            .limit(max(1, min(limit, 200)))
        )
        return list(self.db.scalars(statement).all())

    def get_by_id(self, message_id: int) -> ConversationMessage | None:
        return self.db.get(ConversationMessage, message_id)

    def delete(self, message: ConversationMessage) -> None:
        self.db.delete(message)
        self.db.commit()

