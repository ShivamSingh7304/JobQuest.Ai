"""Persisted human review decisions for AI-generated outputs."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from jobquest_ai.database.connection import Base


class HumanFeedback(Base):
    __tablename__ = "human_feedback"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)

    # A review can point to an assistant message, an entire conversation, or
    # an output produced by one of the typed workflows.
    conversation_id: Mapped[int | None] = mapped_column(
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    message_id: Mapped[int | None] = mapped_column(
        ForeignKey("conversation_messages.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    workflow_name: Mapped[str | None] = mapped_column(
        String(100), nullable=True, index=True
    )
    workflow_output_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    user = relationship("User", back_populates="human_feedback")
    conversation = relationship("Conversation", back_populates="human_feedback")
    message = relationship("ConversationMessage", back_populates="human_feedback")
