
import pytest

from src.jobquest_ai.resume.resume_tailor import (
    ResumeTailoringError,
    tailor_resume,
)


def test_empty_resume_is_rejected():
    with pytest.raises(ResumeTailoringError, match="Resume content is empty"):
        tailor_resume(
            resume="",
            job_description="Python Developer Intern",
        )


def test_empty_job_description_is_rejected():
    with pytest.raises(
        ResumeTailoringError,
        match="Job description cannot be empty",
    ):
        tailor_resume(
            resume="Python, SQL, Flask",
            job_description="",
        )


def test_oversized_resume_is_rejected():
    with pytest.raises(
        ResumeTailoringError,
        match="Resume text exceeds",
    ):
        tailor_resume(
            resume="A" * 25001,
            job_description="Python Developer Intern",
        )


def test_oversized_job_description_is_rejected():
    with pytest.raises(
        ResumeTailoringError,
        match="Job description exceeds",
    ):
        tailor_resume(
            resume="Python, SQL, Flask",
            job_description="A" * 15001,
        )
