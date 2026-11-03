from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from jobquest_ai.api.schemas import (
    JobMatchRequest,
    JobMatchResponse,
    SaveJobRequest,
    SavedJobResponse,
)
from jobquest_ai.auth.dependencies import get_current_user
from jobquest_ai.database.connection import get_db
from jobquest_ai.database.models.user import User
from jobquest_ai.database.repositories.resume_repository import ResumeRepository
from jobquest_ai.database.repositories.job_repository import JobRepository
from jobquest_ai.jobs.job_service import JobService, JobServiceError

router = APIRouter(prefix="/jobs", tags=["Jobs"])


@router.post(
    "/save",
    response_model=SavedJobResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Save one selected external job",
)
def save_job(
    payload: SaveJobRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> SavedJobResponse:
    _ = current_user
    location = ", ".join(
        value.strip()
        for value in payload.location_restrictions
        if value.strip()
    ) or None

    if not payload.external_id.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="external_id cannot be empty.",
        )

    posted_at = None
    if payload.published_at:
        try:
            posted_at = datetime.fromisoformat(
                payload.published_at.replace("Z", "+00:00")
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="published_at must be a valid ISO date or datetime.",
            ) from exc

    try:
        job = JobRepository(db).upsert_external_job(
            source="himalayas",
            external_job_id=payload.external_id.strip(),
            title=payload.title.strip(),
            company=payload.company_name.strip(),
            description=payload.description or payload.excerpt,
            location=location,
            work_mode=None,
            employment_type=payload.employment_type,
            apply_url=str(payload.application_url),
            posted_at=posted_at,
        )
    except Exception as exc:
        rollback = getattr(db, "rollback", None)
        if callable(rollback):
            rollback()
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unable to save the selected job.",
        ) from exc

    return SavedJobResponse(
        job_id=job.id,
        external_job_id=job.external_job_id,
        source=job.source,
        title=job.title,
        company=job.company,
        description=job.description,
        location=job.location,
        employment_type=job.employment_type,
        apply_url=job.apply_url,
        posted_at=job.posted_at,
    )


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
