from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from jobquest_ai.database.connection import Base


class ConversationMessage(Base):
    __tablename__ = "conversation_messages"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)

    conversation_id: Mapped[int] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # "user" or "assistant"
    role: Mapped[str] = mapped_column(String(20), nullable=False)

    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Monotonically increasing within a conversation; used for stable ordering.
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    conversation: Mapped["Conversation"] = relationship(  # noqa: F821
        back_populates="messages"
    )

    human_feedback: Mapped[list["HumanFeedback"]] = relationship(
        "HumanFeedback",
        back_populates="message",
        cascade="all, delete-orphan",
    )

