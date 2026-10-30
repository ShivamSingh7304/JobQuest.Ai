"""Typed orchestration for preparing applications with approval gating."""

from dataclasses import dataclass
from typing import Any, Callable

from jobquest_ai.human_review.approval import (
    ApprovalResult,
    ReviewDecision,
    check_approval,
)
from jobquest_ai.tools.application_tools import (
    prepare_application,
    summarize_application_status,
)


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
) -> ApplicationWorkflowResult:
    """Prepare an application and stop unless explicit approval is present.

    ``job_id`` and ``resume_id`` are retained as context for callers and
    validation layers. This workflow does not submit an application; even an
    approved result only tells the caller that a later submission action is
    allowed.
    """

    if not isinstance(company, str) or not company.strip():
        raise ValueError("Company cannot be empty.")
    if not isinstance(role, str) or not role.strip():
        raise ValueError("Role cannot be empty.")
    if job_id is not None and (not isinstance(job_id, int) or job_id <= 0):
        raise ValueError("job_id must be a positive integer when provided.")
    if resume_id is not None and (not isinstance(resume_id, int) or resume_id <= 0):
        raise ValueError("resume_id must be a positive integer when provided.")

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

        approval = check_approval(
            approved,
            decision=review_decision,
            feedback=review_feedback,
        )
        if not approval.approved:
            return ApplicationWorkflowResult(
                company=company,
                role=role,
                job_id=job_id,
                resume_id=resume_id,
                job_description=job_description,
                status="pending_approval",
                readiness_checklist=checklist,
                approval=approval,
                next_steps=(
                    "Review the job requirements and tailored materials.",
                    "Confirm the resume and application details are accurate.",
                    "Provide explicit approval before submitting anything.",
                ),
            )

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

        return ApplicationWorkflowResult(
            company=company,
            role=role,
            job_id=job_id,
            resume_id=resume_id,
            job_description=job_description,
            status="approved_for_submission",
            readiness_checklist=checklist,
            approval=approval,
            next_steps=(
                "Perform the separately implemented submission action.",
                "Record the resulting application status after submission.",
            ),
            submission_allowed=True,
        )
    except ApplicationWorkflowError:
        raise
    except Exception as exc:
        raise ApplicationWorkflowError(f"Application workflow failed: {exc}") from exc


__all__ = [
    "ApplicationWorkflowError",
    "ApplicationWorkflowResult",
    "run_application_workflow",
]
