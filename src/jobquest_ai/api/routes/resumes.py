from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from jobquest_ai.api.schemas import ResumeTailorRequest
from jobquest_ai.auth.dependencies import get_current_user
from jobquest_ai.database.connection import get_db
from jobquest_ai.database.models.user import User
from jobquest_ai.database.repositories.resume_repository import ResumeRepository
from jobquest_ai.resume.resume_tailor import (
    ResumeTailoringError,
    TailoredResume,
    tailor_resume,
)

router = APIRouter(prefix="/resumes", tags=["Resumes"])


@router.post(
    "/{resume_id}/tailor",
    response_model=TailoredResume,
    summary="Tailor a resume to a target job description",
)
def tailor_resume_for_job(
    resume_id: int,
    payload: ResumeTailorRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> TailoredResume:
    resume = ResumeRepository(db).get_by_id(resume_id)

    if resume is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Resume not found.",
        )

    if resume.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this resume.",
        )

    if not payload.job_description.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Job description cannot be empty.",
        )

    resume_text = resume.extracted_text
    if not isinstance(resume_text, str) or not resume_text.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Resume does not contain readable text. Parse the resume first.",
        )

    if len(resume_text) > 25_000:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Resume text exceeds 25000 characters.",
        )

    try:
        return tailor_resume(
            resume=resume_text,
            job_description=payload.job_description,
        )
    except ResumeTailoringError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Resume tailoring failed: {exc}",
        ) from exc
