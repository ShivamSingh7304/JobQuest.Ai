from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from jobquest_ai.api.schemas import (
    ApplicationCreate,
    ApplicationResponse,
    ApplicationStatus,
    ApplicationUpdate,
)
from jobquest_ai.auth.dependencies import get_current_user
from jobquest_ai.database.connection import get_db
from jobquest_ai.database.models.application import Application
from jobquest_ai.database.models.user import User
from jobquest_ai.database.repositories.application_repository import (
    ApplicationRepository,
)
from jobquest_ai.database.repositories.job_repository import JobRepository
from jobquest_ai.database.repositories.resume_repository import ResumeRepository

router = APIRouter(prefix="/applications", tags=["Applications"])


def _get_owned_application(
    application_id: int,
    current_user: User,
    db: Session,
) -> Application:
    application = ApplicationRepository(db).get_by_id(application_id)
    if application is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Application not found.",
        )
    if application.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this application.",
        )
    return application


def _validate_references(
    payload: ApplicationCreate,
    current_user: User,
    db: Session,
) -> None:
    if JobRepository(db).get_by_id(payload.job_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Job not found.",
        )

    if payload.resume_id is None:
        return

    resume = ResumeRepository(db).get_by_id(payload.resume_id)
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


@router.post(
    "",
    response_model=ApplicationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an application",
)
def create_application(
    payload: ApplicationCreate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ApplicationResponse:
    _validate_references(payload, current_user, db)
    application = ApplicationRepository(db).create(
        user_id=current_user.id,
        job_id=payload.job_id,
        resume_id=payload.resume_id,
        status=payload.status,
        notes=payload.notes,
    )
    return ApplicationResponse.model_validate(application)


@router.get(
    "",
    response_model=list[ApplicationResponse],
    summary="List the current user's applications",
)
def list_applications(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    status_filter: Annotated[
        ApplicationStatus | None,
        Query(alias="status", description="Optional application status filter."),
    ] = None,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
) -> list[ApplicationResponse]:
    applications = ApplicationRepository(db).list_by_user(
        user_id=current_user.id,
        status=status_filter,
        skip=skip,
        limit=limit,
    )
    return [ApplicationResponse.model_validate(item) for item in applications]


@router.patch(
    "/{application_id}",
    response_model=ApplicationResponse,
    summary="Update an application",
)
def update_application(
    application_id: int,
    payload: ApplicationUpdate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ApplicationResponse:
    application = _get_owned_application(application_id, current_user, db)
    next_status = payload.status or application.status
    updated = ApplicationRepository(db).update_status(
        application,
        status=next_status,
        notes=payload.notes,
    )
    return ApplicationResponse.model_validate(updated)


@router.delete(
    "/{application_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an application",
)
def delete_application(
    application_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> None:
    application = _get_owned_application(application_id, current_user, db)
    ApplicationRepository(db).delete(application)
