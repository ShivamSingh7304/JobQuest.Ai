"""Authenticated dashboard data for the current user's Overview page."""

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from jobquest_ai.api.schemas import OverviewResponse
from jobquest_ai.auth.dependencies import get_current_user
from jobquest_ai.database.connection import get_db
from jobquest_ai.database.models.user import User
from jobquest_ai.database.repositories.application_repository import ApplicationRepository
from jobquest_ai.database.repositories.resume_repository import ResumeRepository

router = APIRouter(prefix="/overview", tags=["Overview"])


@router.get("", response_model=OverviewResponse)
def get_overview(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> OverviewResponse:
    applications = ApplicationRepository(db).list_by_user(current_user.id, limit=100)
    resumes = ResumeRepository(db).list_by_user(current_user.id, limit=100)
    active_statuses = {"saved", "pending_approval", "approved", "submitted", "interviewing"}
    recent = [
        {
            "id": item.id,
            "role": item.job.title if item.job else "Unknown role",
            "company": item.job.company if item.job else "Unknown company",
            "stage": {
                "pending_approval": "In review",
                "approved": "Approved",
                "submitted": "Applied",
                "interviewing": "Interview",
            }.get(item.status, item.status.replace("_", " ").title()),
            "status": item.status,
            "updated_at": item.updated_at,
        }
        for item in applications[:5]
    ]
    return OverviewResponse(
        active_applications=sum(item.status in active_statuses for item in applications),
        interviewing_applications=sum(item.status == "interviewing" for item in applications),
        saved_opportunities=sum(item.status == "saved" for item in applications),
        resume_count=len(resumes),
        recent_applications=recent,
    )
