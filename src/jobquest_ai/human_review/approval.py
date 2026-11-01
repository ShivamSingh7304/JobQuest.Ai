"""Human approval primitives for irreversible JobQuest.Ai actions."""

from dataclasses import dataclass
from typing import Any, Literal


ReviewDecision = Literal["approve", "request_changes"]
ApprovalState = Literal["approved", "pending", "changes_requested"]


@dataclass(frozen=True)
class ApprovalResult:
    """The outcome of checking whether a user approved an action."""

    approved: bool
    state: ApprovalState
    message: str
    decision: ReviewDecision | None = None
    feedback: str | None = None


def validate_review(
    decision: str,
    feedback: str | None = None,
) -> ApprovalResult:
    """Validate a human review and convert it into a workflow gate result."""

    if decision not in {"approve", "request_changes"}:
        raise ValueError("Decision must be 'approve' or 'request_changes'.")
    if feedback is not None:
        feedback = feedback.strip()
        if len(feedback) > 32_000:
            raise ValueError("Feedback must be at most 32000 characters.")
        if not feedback:
            feedback = None

    if decision == "approve":
        return ApprovalResult(
            approved=True,
            state="approved",
            message="User approval received; the requested action may proceed.",
            decision=decision,
            feedback=feedback,
        )

    return ApprovalResult(
        approved=False,
        state="changes_requested",
        message="The user requested changes; the workflow must not proceed.",
        decision=decision,
        feedback=feedback,
    )


def check_approval(
    approved: bool = False,
    *,
    decision: ReviewDecision | None = None,
    feedback: str | None = None,
) -> ApprovalResult:
    """Return an approval decision without performing any action."""

    if decision is not None:
        return validate_review(decision, feedback)

    if approved:
        return validate_review("approve")

    return ApprovalResult(
        approved=False,
        state="pending",
        message=(
            "Pending user approval. No application was submitted and no "
            "irreversible action was performed."
        ),
    )


def check_persisted_approval(
    repository: Any,
    *,
    user_id: int,
    workflow_name: str,
    workflow_output_id: str | int,
) -> ApprovalResult:
    """Check the latest persisted review for an exact user/output pair."""

    if not isinstance(user_id, int) or user_id <= 0:
        raise ValueError("user_id must be a positive integer.")
    if not isinstance(workflow_name, str) or not workflow_name.strip():
        raise ValueError("workflow_name cannot be empty.")
    if not isinstance(workflow_output_id, (str, int)) or (
        isinstance(workflow_output_id, str) and not workflow_output_id.strip()
    ):
        raise ValueError("workflow_output_id cannot be empty.")
    if repository is None or not hasattr(repository, "get_latest_decision_for_output"):
        raise ValueError("A feedback repository is required for persisted approval.")

    feedback = repository.get_latest_decision_for_output(
        user_id=user_id,
        workflow_name=workflow_name.strip(),
        workflow_output_id=(
            workflow_output_id.strip()
            if isinstance(workflow_output_id, str)
            else workflow_output_id
        ),
    )
    if feedback is None:
        return ApprovalResult(
            approved=False,
            state="pending",
            message=(
                "No persisted approval exists for this user and workflow output. "
                "The application action remains blocked."
            ),
        )

    return validate_review(feedback.decision, feedback.feedback)


__all__ = [
    "ApprovalResult",
    "ApprovalState",
    "ReviewDecision",
    "check_approval",
    "check_persisted_approval",
    "validate_review",
]
