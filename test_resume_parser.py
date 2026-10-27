
from pathlib import Path

from src.jobquest_ai.resume.resume_parser import (
    parse_resume,
    ResumeParsingError,
)


resume_path = Path("sample_resume2.docx")

try:
    result = parse_resume(resume_path)

    print("File:", result["file_name"])
    print("Format:", result["file_type"])
    print("Characters:", result["character_count"])
    print("\nExtracted resume text:\n")
    print(result["text"])

except ResumeParsingError as exc:
    print("Resume parsing failed:", exc)
