"""Human approval primitives for irreversible JobQuest.Ai actions."""

from dataclasses import dataclass
from typing import Literal


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


__all__ = [
    "ApprovalResult",
    "ApprovalState",
    "ReviewDecision",
    "check_approval",
    "validate_review",
]
