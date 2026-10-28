
"""Workflow for resume analysis in JobQuest.Ai."""

from pathlib import Path
from typing import Any

from jobquest_ai.tools.resume_tools import analyze_uploaded_resume


def run_resume_workflow(file_path: str) -> dict[str, Any]:
    """
    Coordinate resume analysis and flag the result for human review.

    Args:
        file_path: Path to the uploaded resume.

    Returns:
        A dictionary containing workflow status, analysis, and review details.

    Raises:
        ValueError: If the supplied file path is empty.
        FileNotFoundError: If the resume file does not exist.
        Exception: Errors from the underlying resume tool propagate to the caller.
    """
    if not isinstance(file_path, str) or not file_path.strip():
        raise ValueError("Resume file path cannot be empty.")

    path = Path(file_path)

    # Step 1: Execute the existing resume analysis tool.
    analysis_result = analyze_uploaded_resume(str(path))

    # Step 2: Verify that the tool reported success.
    if not isinstance(analysis_result, dict):
        raise ValueError("Resume analysis returned an invalid result.")

    if not analysis_result.get("success"):
        raise ValueError("Resume analysis could not be completed.")

    if analysis_result.get("analysis") is None:
        raise ValueError("Resume analysis result is missing the analysis data.")

    # Step 3: Flag the result for human review.
    # This marks the review requirement; it does not create a review
    # request in the human_review module yet.
    return {
        "workflow": "resume_analysis",
        "status": "awaiting_review",
        "success": True,
        "file_name": analysis_result.get("file_name", path.name),
        "analysis": analysis_result["analysis"],
        "human_review": {
            "required": True,
            "status": "pending",
            "reason": (
                "The user must verify the extracted resume details "
                "and analysis before relying on the results."
            ),
        },
        "next_action": "review_resume_analysis",
    }
