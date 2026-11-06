"""Typed orchestration for preparing applications with approval gating."""

import logging
from dataclasses import dataclass
from typing import Any, Callable

from jobquest_ai.human_review.approval import (
    ApprovalResult,
    ReviewDecision,
    check_persisted_approval,
)
from jobquest_ai.tools.application_tools import (
    prepare_application,
    summarize_application_status,
)

logger = logging.getLogger(__name__)


class ApplicationWorkflowError(RuntimeError):
    """A dependency or validation failure in the application workflow."""


@dataclass(frozen=True)
class ApplicationWorkflowResult:
    """Readiness and next steps for an application; never a submission."""

    company: str
    role: str
    job_id: int | None
    resume_id: int | None
    job_description: str | None
    workflow_output_id: int | None
    status: str
    readiness_checklist: str
    approval: ApprovalResult
    next_steps: tuple[str, ...]
    submission_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow": "application_preparation",
            "company": self.company,
            "role": self.role,
            "job_id": self.job_id,
            "resume_id": self.resume_id,
            "job_description": self.job_description,
            "workflow_output_id": self.workflow_output_id,
            "status": self.status,
            "readiness_checklist": self.readiness_checklist,
            "approval": {
                "approved": self.approval.approved,
                "state": self.approval.state,
                "message": self.approval.message,
            },
            "next_steps": list(self.next_steps),
            "submission_allowed": self.submission_allowed,
        }


def _invoke_tool(tool: Any, payload: dict[str, Any]) -> Any:
    invoke: Callable[[dict[str, Any]], Any] | None = getattr(tool, "invoke", None)
    if invoke is not None:
        return invoke(payload)
    return tool(**payload)


def run_application_workflow(
    company: str,
    role: str,
    *,
    resume_ready: bool = False,
    job_id: int | None = None,
    resume_id: int | None = None,
    job_description: str | None = None,
    approved: bool = False,
    review_decision: ReviewDecision | None = None,
    review_feedback: str | None = None,
    user_id: int | None = None,
    workflow_output_id: int | None = None,
    feedback_repository: Any | None = None,
    workflow_output_repository: Any | None = None,
    output_key: str | None = None,
) -> ApplicationWorkflowResult:
    """Prepare an application and stop unless persisted approval is present.

    ``job_id`` and ``resume_id`` are retained as context for callers and
    validation layers. This workflow does not submit an application; even an
    approved result only tells the caller that a later submission action is
    allowed. ``approved``, ``review_decision``, and ``review_feedback`` are
    retained for compatibility in the result context but cannot bypass the
    persisted approval check.
    """

    logger.info("application_workflow_started user_id=%s job_id=%s resume_id=%s", user_id, job_id, resume_id)
    if not isinstance(company, str) or not company.strip():
        raise ValueError("Company cannot be empty.")
    if not isinstance(role, str) or not role.strip():
        raise ValueError("Role cannot be empty.")
    if job_id is not None and (not isinstance(job_id, int) or job_id <= 0):
        raise ValueError("job_id must be a positive integer when provided.")
    if resume_id is not None and (not isinstance(resume_id, int) or resume_id <= 0):
        raise ValueError("resume_id must be a positive integer when provided.")
    if user_id is not None and workflow_output_repository is not None and workflow_output_id is None:
        output = workflow_output_repository.create(
            user_id=user_id,
            workflow_name="application_preparation",
            output_type="application",
            output_key=output_key,
            payload={
                "company": company,
                "role": role,
                "job_id": job_id,
                "resume_id": resume_id,
                "job_description": job_description,
            },
            status="pending_review",
        )
        workflow_output_id = output.id

    if (
        user_id is None
        or workflow_output_id is None
        or feedback_repository is None
    ):
        persisted_approval = ApprovalResult(
            approved=False,
            state="pending",
            message=(
                "Persisted approval context is required: provide user_id, "
                "workflow_output_id, and feedback_repository."
            ),
        )
    else:
        persisted_approval = check_persisted_approval(
            feedback_repository,
            user_id=user_id,
            workflow_name="application_preparation",
            workflow_output_id=workflow_output_id,
        )

    company = company.strip()
    role = role.strip()

    try:
        checklist = _invoke_tool(
            prepare_application,
            {"company": company, "role": role, "resume_ready": resume_ready},
        )
        if not isinstance(checklist, str) or not checklist.strip():
            raise ApplicationWorkflowError(
                "Application preparation returned an invalid checklist."
            )

        approval = persisted_approval
        if not approval.approved:
            result = ApplicationWorkflowResult(
                company=company,
                role=role,
                job_id=job_id,
                resume_id=resume_id,
                job_description=job_description,
                workflow_output_id=workflow_output_id,
                status="pending_approval",
                readiness_checklist=checklist,
                approval=approval,
                next_steps=(
                    "Review the job requirements and tailored materials.",
                    "Confirm the resume and application details are accurate.",
                    "Provide explicit approval before submitting anything.",
                ),
            )
            if workflow_output_repository is not None and user_id is not None:
                payload = result.to_dict()
                payload["workflow_output_id"] = result.workflow_output_id
                update_payload = getattr(
                    workflow_output_repository,
                    "update_payload_for_user",
                    None,
                )
                if update_payload is not None:
                    update_payload(workflow_output_id, user_id, payload)
            return result

        status_summary = _invoke_tool(
            summarize_application_status,
            {
                "company": company,
                "role": role,
                "status": "approved",
                "next_step": "Submit only after the caller performs its approved submission action.",
            },
        )
        if not isinstance(status_summary, str) or not status_summary.strip():
            raise ApplicationWorkflowError(
                "Application status summarization returned an invalid result."
            )

        if workflow_output_repository is not None and user_id is not None:
            workflow_output_repository.update_status_for_user(
                workflow_output_id, user_id, "approved"
            )

        result = ApplicationWorkflowResult(
            company=company,
            role=role,
            job_id=job_id,
            resume_id=resume_id,
            job_description=job_description,
            workflow_output_id=workflow_output_id,
            status="approved_for_submission",
            readiness_checklist=checklist,
            approval=approval,
            next_steps=(
                "Perform the separately implemented submission action.",
                "Record the resulting application status after submission.",
            ),
            submission_allowed=True,
        )
        if workflow_output_repository is not None and user_id is not None:
            payload = result.to_dict()
            payload["workflow_output_id"] = result.workflow_output_id
            update_payload = getattr(
                workflow_output_repository,
                "update_payload_for_user",
                None,
            )
            if update_payload is not None:
                update_payload(workflow_output_id, user_id, payload)
        logger.info("application_workflow_completed user_id=%s workflow_output_id=%s approved=%s", user_id, result.workflow_output_id, result.submission_allowed)
        return result
    except ApplicationWorkflowError:
        raise
    except Exception as exc:
        logger.exception("application_workflow_failed user_id=%s", user_id)
        raise ApplicationWorkflowError(f"Application workflow failed: {exc}") from exc


__all__ = [
    "ApplicationWorkflowError",
    "ApplicationWorkflowResult",
    "run_application_workflow",
]
