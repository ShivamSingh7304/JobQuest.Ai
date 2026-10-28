
"""Tools for resume processing in JobQuest.Ai."""

from pathlib import Path
from typing import Any

from jobquest_ai.resume.resume_parser import parse_resume
from jobquest_ai.resume.resume_analyzer import analyze_resume


def analyze_uploaded_resume(file_path: str) -> dict[str, Any]:
    """Parse and analyze an uploaded resume."""
    path = Path(file_path)

    if not path.is_file():
        raise FileNotFoundError(f"Resume file not found: {file_path}")

    parsed_resume = parse_resume(str(path))

    # The parser returns a dictionary, not a string.
    if isinstance(parsed_resume, dict):
        resume_text = parsed_resume.get("text", "")
    elif isinstance(parsed_resume, str):
        # Also support parsers that return text directly.
        resume_text = parsed_resume
    else:
        raise ValueError("Resume parser returned an invalid result.")

    if not isinstance(resume_text, str) or not resume_text.strip():
        raise ValueError("No readable text was extracted from the resume.")

    analysis = analyze_resume(resume_text)

    return {
        "success": True,
        "file_name": path.name,
        "analysis": analysis,
    }
