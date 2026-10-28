from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from jobquest_ai.api.schemas import JobMatchRequest, JobMatchResponse
from jobquest_ai.auth.dependencies import get_current_user
from jobquest_ai.database.connection import get_db
from jobquest_ai.database.models.user import User
from jobquest_ai.database.repositories.resume_repository import ResumeRepository
from jobquest_ai.jobs.job_service import JobService, JobServiceError

router = APIRouter(prefix="/jobs", tags=["Jobs"])


def _get_candidate_profile(resume_id: int, current_user: User, db: Session) -> dict:
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

    profile = resume.parsed_data
    if not isinstance(profile, dict) or not profile:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Resume does not contain usable profile data. Analyze the resume first.",
        )

    return profile


@router.post(
    "/match",
    response_model=JobMatchResponse,
    summary="Find and rank jobs against a resume",
)
@router.post(
    "/search",
    response_model=JobMatchResponse,
    include_in_schema=False,
)
def match_jobs(
    payload: JobMatchRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> JobMatchResponse:
    candidate_profile = _get_candidate_profile(
        payload.resume_id,
        current_user,
        db,
    )

    try:
        with JobService() as service:
            result = service.search_and_match(
                candidate_profile=candidate_profile,
                query=payload.query,
                country=payload.country,
                max_pages=payload.max_pages,
                top_k=payload.limit,
            )
    except JobServiceError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc

    return JobMatchResponse.model_validate(result)
