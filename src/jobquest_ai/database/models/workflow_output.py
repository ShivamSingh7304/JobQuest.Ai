"""Persisted, user-owned outputs produced by typed workflows."""

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, JSON, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from jobquest_ai.database.connection import Base


class WorkflowOutput(Base):
    __tablename__ = "workflow_outputs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    workflow_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    output_type: Mapped[str] = mapped_column(String(50), nullable=False)
    output_key: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending_review"
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    parent_output_id: Mapped[int | None] = mapped_column(
        ForeignKey("workflow_outputs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
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

    user = relationship("User", back_populates="workflow_outputs")
    parent = relationship(
        "WorkflowOutput", remote_side=[id], back_populates="revisions"
    )
    revisions = relationship("WorkflowOutput", back_populates="parent")
    human_feedback = relationship(
        "HumanFeedback", back_populates="workflow_output"
    )
