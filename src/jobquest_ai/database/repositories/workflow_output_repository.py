"""User-scoped persistence for workflow outputs and revisions."""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from jobquest_ai.database.models.workflow_output import WorkflowOutput


class WorkflowOutputRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_by_id(self, output_id: int) -> WorkflowOutput | None:
        return self.db.get(WorkflowOutput, output_id)

    def get_by_id_for_user(
        self, output_id: int, user_id: int
    ) -> WorkflowOutput | None:
        statement = select(WorkflowOutput).where(
            WorkflowOutput.id == output_id,
            WorkflowOutput.user_id == user_id,
        )
        return self.db.scalar(statement)

    def get_by_key_for_user(
        self,
        *,
        user_id: int,
        workflow_name: str,
        output_key: str,
    ) -> WorkflowOutput | None:
        statement = select(WorkflowOutput).where(
            WorkflowOutput.user_id == user_id,
            WorkflowOutput.workflow_name == workflow_name,
            WorkflowOutput.output_key == output_key,
        ).order_by(WorkflowOutput.version.desc(), WorkflowOutput.id.desc())
        return self.db.scalar(statement)

    def list_by_user(
        self,
        user_id: int,
        *,
        workflow_name: str | None = None,
        status: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[WorkflowOutput]:
        statement = select(WorkflowOutput).where(WorkflowOutput.user_id == user_id)
        if workflow_name:
            statement = statement.where(WorkflowOutput.workflow_name == workflow_name)
        if status:
            statement = statement.where(WorkflowOutput.status == status)
        statement = (
            statement.order_by(WorkflowOutput.updated_at.desc())
            .offset(max(skip, 0))
            .limit(max(1, min(limit, 100)))
        )
        return list(self.db.scalars(statement).all())

    def create(
        self,
        *,
        user_id: int,
        workflow_name: str,
        output_type: str,
        payload: dict[str, Any],
        output_key: str | None = None,
        status: str = "pending_review",
        parent_output_id: int | None = None,
    ) -> WorkflowOutput:
        version = 1
        if parent_output_id is not None:
            parent = self.get_by_id_for_user(parent_output_id, user_id)
            if parent is None:
                raise PermissionError("You do not have access to the parent workflow output.")
            version = int(
                self.db.scalar(
                    select(func.max(WorkflowOutput.version)).where(
                        WorkflowOutput.user_id == user_id,
                        WorkflowOutput.workflow_name == workflow_name,
                        WorkflowOutput.output_key == parent.output_key,
                    )
                )
                or parent.version
            ) + 1

        item = WorkflowOutput(
            user_id=user_id,
            workflow_name=workflow_name,
            output_type=output_type,
            output_key=output_key,
            payload=payload,
            status=status,
            version=version,
            parent_output_id=parent_output_id,
        )
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def create_revision(
        self,
        parent: WorkflowOutput,
        *,
        payload: dict[str, Any],
        status: str = "pending_review",
    ) -> WorkflowOutput:
        item = self.create(
            user_id=parent.user_id,
            workflow_name=parent.workflow_name,
            output_type=parent.output_type,
            output_key=parent.output_key,
            payload=payload,
            status=status,
            parent_output_id=parent.id,
        )
        parent.status = "superseded"
        self.db.commit()
        self.db.refresh(item)
        return item

    def update_status_for_user(
        self,
        output_id: int,
        user_id: int,
        status: str,
    ) -> WorkflowOutput:
        item = self.get_by_id_for_user(output_id, user_id)
        if item is None:
            raise LookupError("Workflow output not found.")
        item.status = status
        self.db.commit()
        self.db.refresh(item)
        return item

    def update_payload_for_user(
        self,
        output_id: int,
        user_id: int,
        payload: dict[str, Any],
    ) -> WorkflowOutput:
        item = self.get_by_id_for_user(output_id, user_id)
        if item is None:
            raise LookupError("Workflow output not found.")
        item.payload = payload
        self.db.commit()
        self.db.refresh(item)
        return item
