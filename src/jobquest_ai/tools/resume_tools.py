
"""Tools for resume processing in JobQuest.Ai."""

from pathlib import Path
from typing import Any

from langchain_core.tools import tool

from jobquest_ai.resume.resume_parser import parse_resume
from jobquest_ai.resume.resume_analyzer import analyze_resume


@tool
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

    parsed_resume = parse_resume(str(path))

    if not isinstance(parsed_resume, dict) or not parsed_resume.get("text", "").strip():
        raise ValueError("No readable text was extracted from the resume.")

    analysis = analyze_resume(parsed_resume)

    return {
        "success": True,
        "file_name": path.name,
        "analysis": analysis.model_dump(),
    }


TOOLS = [analyze_uploaded_resume]
