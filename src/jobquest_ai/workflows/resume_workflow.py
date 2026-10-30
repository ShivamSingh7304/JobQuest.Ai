"""Typed orchestration for resume analysis and role-specific guidance."""

from dataclasses import dataclass
from typing import Any, Callable

from jobquest_ai.resume.resume_analyzer import analyze_resume
from jobquest_ai.resume.resume_tailor import TailoredResume, tailor_resume
from jobquest_ai.tools.resume_tools import analyze_uploaded_resume


class ResumeWorkflowError(RuntimeError):
    """A dependency or validation failure in the resume workflow."""


@dataclass(frozen=True)
class ResumeWorkflowResult:
    """Structured, reviewable output from the resume workflow."""

    target_role: str
    analysis: dict[str, Any]
    tailoring: TailoredResume
    status: str = "awaiting_review"
    original_content_unchanged: bool = True
    next_steps: tuple[str, ...] = (
        "Review each suggested change against the original resume.",
        "Verify every claim before copying tailored content into an application.",
    )

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly representation for API or agent callers."""

        return {
            "workflow": "resume_analysis_and_tailoring",
            "status": self.status,
            "target_role": self.target_role,
            "analysis": self.analysis,
            "tailoring": self.tailoring.model_dump(),
            "original_content_unchanged": self.original_content_unchanged,
            "human_review": {
                "required": True,
                "status": "pending",
                "reason": "Tailored suggestions require user verification.",
            },
            "next_steps": list(self.next_steps),
        }


def _invoke_tool(tool: Any, payload: dict[str, Any]) -> Any:
    """Invoke a LangChain tool while keeping the workflow easy to test."""

    invoke: Callable[[dict[str, Any]], Any] | None = getattr(tool, "invoke", None)
    if invoke is not None:
        return invoke(payload)
    return tool(**payload)


def _validate_inputs(resume_content: str, target_role: str) -> tuple[str, str]:
    if not isinstance(resume_content, str) or not resume_content.strip():
        raise ValueError("Resume content cannot be empty.")
    if not isinstance(target_role, str) or not target_role.strip():
        raise ValueError("Target role cannot be empty.")
    return resume_content.strip(), target_role.strip()


def run_resume_workflow(
    resume_content: str,
    target_role: str,
    *,
    file_path: str | None = None,
) -> ResumeWorkflowResult:
    """Analyze resume content and produce role-specific, reviewable guidance.

    ``resume_content`` is the source of truth and is never mutated. When a
    PDF/DOCX ``file_path`` is supplied, the existing upload tool performs the
    parsing and analysis; otherwise the analyzer consumes the supplied text.
    ``target_role`` is used as the tailoring brief and may be a full job
    description supplied by the caller.
    """

    content, role = _validate_inputs(resume_content, target_role)

    try:
        if file_path:
            analysis_result = _invoke_tool(
                analyze_uploaded_resume,
                {"file_path": file_path},
            )
            if not isinstance(analysis_result, dict) or not analysis_result.get(
                "success"
            ):
                raise ResumeWorkflowError("Resume analysis could not be completed.")
            analysis = analysis_result.get("analysis")
            if not isinstance(analysis, dict):
                raise ResumeWorkflowError("Resume analysis returned no structured data.")
        else:
            analysis = analyze_resume({"text": content}).model_dump()

        tailored = tailor_resume(
            resume=content,
            job_description=role,
            analysis=analysis,
        )
    except ResumeWorkflowError:
        raise
    except Exception as exc:
        raise ResumeWorkflowError(f"Resume workflow failed: {exc}") from exc

    return ResumeWorkflowResult(
        target_role=role,
        analysis=analysis,
        tailoring=tailored,
    )


__all__ = ["ResumeWorkflowError", "ResumeWorkflowResult", "run_resume_workflow"]
