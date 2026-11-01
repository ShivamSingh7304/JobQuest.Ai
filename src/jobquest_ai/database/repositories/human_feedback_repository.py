"""User-scoped persistence for human review decisions."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from jobquest_ai.database.models.conversation import Conversation
from jobquest_ai.database.models.conversation_message import ConversationMessage
from jobquest_ai.database.models.human_feedback import HumanFeedback
from jobquest_ai.database.models.workflow_output import WorkflowOutput


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

    def get_latest_decision_for_output(
        self,
        *,
        user_id: int,
        workflow_name: str,
        workflow_output_id: str | int,
    ) -> HumanFeedback | None:
        """Return the latest review for one user-owned workflow output."""

        filters = [
            HumanFeedback.user_id == user_id,
            HumanFeedback.workflow_name == workflow_name,
        ]
        if isinstance(workflow_output_id, int):
            filters.append(HumanFeedback.workflow_output_record_id == workflow_output_id)
        else:
            filters.append(HumanFeedback.workflow_output_id == workflow_output_id)
        statement = select(HumanFeedback).where(*filters).order_by(
            HumanFeedback.created_at.desc(), HumanFeedback.id.desc()
        ).limit(1)
        return self.db.scalar(statement)

    def _validate_target_ownership(
        self,
        user_id: int,
        *,
        conversation_id: int | None,
        message_id: int | None,
        workflow_name: str | None,
        workflow_output_id: str | None,
        workflow_output_record_id: int | None,
    ) -> None:
        has_conversation_target = conversation_id is not None or message_id is not None
        has_workflow_target = (
            workflow_name is not None
            or workflow_output_id is not None
            or workflow_output_record_id is not None
        )

        if has_conversation_target == has_workflow_target:
            raise ValueError(
                "Provide either a conversation/message target or a workflow output target."
            )

        if has_workflow_target:
            if workflow_output_record_id is not None:
                output = self.db.get(WorkflowOutput, workflow_output_record_id)
                if output is None:
                    raise LookupError("Workflow output not found.")
                if output.user_id != user_id:
                    raise PermissionError("You do not have access to this workflow output.")
                if workflow_name is not None and output.workflow_name != workflow_name:
                    raise ValueError("workflow_name does not match the workflow output.")
                return
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
        workflow_output_record_id: int | None = None,
    ) -> HumanFeedback:
        self._validate_target_ownership(
            user_id,
            conversation_id=conversation_id,
            message_id=message_id,
            workflow_name=workflow_name,
            workflow_output_id=workflow_output_id,
            workflow_output_record_id=workflow_output_record_id,
        )
        if workflow_output_record_id is not None:
            output = self.db.get(WorkflowOutput, workflow_output_record_id)
            if output is not None:
                workflow_name = output.workflow_name
                workflow_output_id = output.output_key or str(output.id)
        elif workflow_name and workflow_output_id:
            output = self.get_workflow_output_for_user(
                user_id=user_id,
                workflow_name=workflow_name,
                workflow_output_id=workflow_output_id,
            )
            if output is not None:
                workflow_output_record_id = output.id
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
            workflow_output_record_id=workflow_output_record_id,
        )
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def get_workflow_output_for_user(
        self,
        *,
        user_id: int,
        workflow_name: str,
        workflow_output_id: str | int,
    ) -> WorkflowOutput | None:
        if isinstance(workflow_output_id, int) or (
            isinstance(workflow_output_id, str) and workflow_output_id.isdigit()
        ):
            output = self.db.get(WorkflowOutput, int(workflow_output_id))
            if output is not None and output.user_id == user_id:
                return output
            return None
        statement = select(WorkflowOutput).where(
            WorkflowOutput.user_id == user_id,
            WorkflowOutput.workflow_name == workflow_name,
            WorkflowOutput.output_key == workflow_output_id,
        )
        return self.db.scalar(statement)

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
