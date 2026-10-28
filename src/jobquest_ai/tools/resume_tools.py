
"""Tools for resume processing in JobQuest.Ai."""

from pathlib import Path
from typing import Any

from jobquest_ai.resume.resume_parser import parse_resume
from jobquest_ai.resume.resume_analyzer import analyze_resume


def analyze_uploaded_resume(file_path: str) -> dict[str, Any]:
    """
    Parse and analyze an uploaded resume.

    Args:
        file_path: Path to the uploaded resume file.

    Returns:
        A dictionary containing the resume analysis.

    Raises:
        FileNotFoundError: If the resume file does not exist.
        ValueError: If no readable resume text is extracted.
    """
    path = Path(file_path)

    if not path.is_file():
        raise FileNotFoundError(f"Resume file not found: {file_path}")

    resume_text = parse_resume(str(path))

    if not isinstance(resume_text, str) or not resume_text.strip():
        raise ValueError("No readable text was extracted from the resume.")

    analysis = analyze_resume(resume_text)

    return {
        "success": True,
        "file_name": path.name,
        "analysis": analysis,
    }
