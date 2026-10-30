"""User-scoped persistence for human review decisions."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from jobquest_ai.database.models.conversation import Conversation
from jobquest_ai.database.models.conversation_message import ConversationMessage
from jobquest_ai.database.models.human_feedback import HumanFeedback


class HumanFeedbackRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, feedback_id: int) -> HumanFeedback | None:
        return self.db.get(HumanFeedback, feedback_id)

    def get_by_id_for_user(
        self, feedback_id: int, user_id: int
    ) -> HumanFeedback | None:
        statement = select(HumanFeedback).where(
            HumanFeedback.id == feedback_id,
            HumanFeedback.user_id == user_id,
        )
        return self.db.scalar(statement)

    def list_by_user(
        self,
        user_id: int,
        *,
        conversation_id: int | None = None,
        message_id: int | None = None,
        workflow_name: str | None = None,
        workflow_output_id: str | None = None,
    ) -> list[HumanFeedback]:
        statement = select(HumanFeedback).where(HumanFeedback.user_id == user_id)
        if conversation_id is not None:
            statement = statement.where(HumanFeedback.conversation_id == conversation_id)
        if message_id is not None:
            statement = statement.where(HumanFeedback.message_id == message_id)
        if workflow_name is not None:
            statement = statement.where(HumanFeedback.workflow_name == workflow_name)
        if workflow_output_id is not None:
            statement = statement.where(
                HumanFeedback.workflow_output_id == workflow_output_id
            )
        statement = statement.order_by(HumanFeedback.created_at.desc())
        return list(self.db.scalars(statement).all())

    def _validate_target_ownership(
        self,
        user_id: int,
        *,
        conversation_id: int | None,
        message_id: int | None,
        workflow_name: str | None,
        workflow_output_id: str | None,
    ) -> None:
        has_conversation_target = conversation_id is not None or message_id is not None
        has_workflow_target = workflow_name is not None or workflow_output_id is not None

        if has_conversation_target == has_workflow_target:
            raise ValueError(
                "Provide either a conversation/message target or a workflow output target."
            )

        if has_workflow_target:
            if not workflow_name or not workflow_output_id:
                raise ValueError(
                    "workflow_name and workflow_output_id are required together."
                )
            return

        if message_id is not None:
            message = self.db.get(ConversationMessage, message_id)
            if message is None:
                raise LookupError("Conversation message not found.")
            if conversation_id is not None and message.conversation_id != conversation_id:
                raise ValueError("message_id does not belong to conversation_id.")
            conversation_id = message.conversation_id

        conversation = self.db.get(Conversation, conversation_id)
        if conversation is None:
            raise LookupError("Conversation not found.")
        if conversation.user_id != user_id:
            raise PermissionError("You do not have access to this conversation.")

    def create(
        self,
        *,
        user_id: int,
        decision: str,
        feedback: str | None = None,
        conversation_id: int | None = None,
        message_id: int | None = None,
        workflow_name: str | None = None,
        workflow_output_id: str | None = None,
    ) -> HumanFeedback:
        self._validate_target_ownership(
            user_id,
            conversation_id=conversation_id,
            message_id=message_id,
            workflow_name=workflow_name,
            workflow_output_id=workflow_output_id,
        )
        if message_id is not None and conversation_id is None:
            message = self.db.get(ConversationMessage, message_id)
            if message is not None:
                conversation_id = message.conversation_id

        item = HumanFeedback(
            user_id=user_id,
            decision=decision,
            feedback=feedback,
            conversation_id=conversation_id,
            message_id=message_id,
            workflow_name=workflow_name,
            workflow_output_id=workflow_output_id,
        )
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def update(
        self,
        item: HumanFeedback,
        *,
        decision: str,
        feedback: str | None,
    ) -> HumanFeedback:
        item.decision = decision
        item.feedback = feedback
        self.db.commit()
        self.db.refresh(item)
        return item
