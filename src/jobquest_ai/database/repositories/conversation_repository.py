from sqlalchemy import select
from sqlalchemy.orm import Session

from jobquest_ai.database.models.conversation import Conversation


class ConversationRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self, user_id: int, title: str | None = None
    ) -> Conversation:
        conversation = Conversation(
            user_id=user_id,
            title=title,
        )
        self.db.add(conversation)
        self.db.commit()
        self.db.refresh(conversation)
        return conversation

    def get_by_id(self, conversation_id: int) -> Conversation | None:
        return self.db.get(Conversation, conversation_id)

    def list_by_user(
        self, user_id: int, skip: int = 0, limit: int = 50
    ) -> list[Conversation]:
        statement = (
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(Conversation.updated_at.desc())
            .offset(max(skip, 0))
            .limit(max(1, min(limit, 100)))
        )
        return list(self.db.scalars(statement).all())

    def update_title(
        self, conversation: Conversation, title: str
    ) -> Conversation:
        conversation.title = title
        self.db.commit()
        self.db.refresh(conversation)
        return conversation

    def delete(self, conversation: Conversation) -> None:
        self.db.delete(conversation)
        self.db.commit()