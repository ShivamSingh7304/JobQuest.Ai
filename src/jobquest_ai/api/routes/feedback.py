"""Authenticated human-in-the-loop feedback endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from jobquest_ai.api.schemas import (
    ApprovalCheckResponse,
    HumanFeedbackCreate,
    HumanFeedbackResponse,
    HumanFeedbackUpdate,
)
from jobquest_ai.auth.dependencies import get_current_user
from jobquest_ai.database.connection import get_db
from jobquest_ai.database.models.user import User
from jobquest_ai.database.repositories.human_feedback_repository import (
    HumanFeedbackRepository,
)
from jobquest_ai.database.repositories.workflow_output_repository import (
    WorkflowOutputRepository,
)
from jobquest_ai.human_review.approval import check_persisted_approval

router = APIRouter(prefix="/feedback", tags=["Human feedback"])


def _response(item) -> HumanFeedbackResponse:
    return HumanFeedbackResponse.model_validate(item)


def _get_owned_feedback(
    feedback_id: int,
    current_user: User,
    db: Session,
):
    repo = HumanFeedbackRepository(db)
    item = repo.get_by_id(feedback_id)
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Feedback not found.",
        )
    if item.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this feedback.",
        )
    return item


def _sync_workflow_output_status(item, db: Session) -> None:
    if item.workflow_output_record_id is None:
        return
    output_status = (
        "approved" if item.decision == "approve" else "changes_requested"
    )
    WorkflowOutputRepository(db).update_status_for_user(
        item.workflow_output_record_id,
        item.user_id,
        output_status,
    )


@router.post(
    "",
    response_model=HumanFeedbackResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit an approval or change request for an AI output",
)
def create_feedback(
    payload: HumanFeedbackCreate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> HumanFeedbackResponse:
    try:
        item = HumanFeedbackRepository(db).create(
            user_id=current_user.id,
            decision=payload.decision,
            feedback=payload.feedback.strip() if payload.feedback else None,
            conversation_id=payload.conversation_id,
            message_id=payload.message_id,
            workflow_name=payload.workflow_name,
            workflow_output_id=payload.workflow_output_id,
            workflow_output_record_id=payload.workflow_output_record_id,
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except PermissionError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    _sync_workflow_output_status(item, db)
    return _response(item)


@router.get(
    "/approval",
    response_model=ApprovalCheckResponse,
    summary="Check persisted approval for a workflow output",
)
def check_workflow_approval(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    workflow_name: str = Query(..., min_length=1, max_length=100),
    workflow_output_id: str = Query(..., min_length=1, max_length=255),
) -> ApprovalCheckResponse:
    result = check_persisted_approval(
        HumanFeedbackRepository(db),
        user_id=current_user.id,
        workflow_name=workflow_name,
        workflow_output_id=workflow_output_id,
    )
    return ApprovalCheckResponse(
        approved=result.approved,
        state=result.state,
        message=result.message,
        decision=result.decision,
        feedback=result.feedback,
    )


@router.get(
    "",
    response_model=list[HumanFeedbackResponse],
    summary="List the current user's feedback",
)
def list_feedback(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    conversation_id: int | None = Query(default=None, gt=0),
    message_id: int | None = Query(default=None, gt=0),
    workflow_name: str | None = Query(default=None, min_length=1, max_length=100),
    workflow_output_id: str | None = Query(
        default=None, min_length=1, max_length=255
    ),
) -> list[HumanFeedbackResponse]:
    items = HumanFeedbackRepository(db).list_by_user(
        current_user.id,
        conversation_id=conversation_id,
        message_id=message_id,
        workflow_name=workflow_name,
        workflow_output_id=workflow_output_id,
    )
    return [_response(item) for item in items]


@router.get(
    "/{feedback_id}",
    response_model=HumanFeedbackResponse,
    summary="Retrieve one of the current user's feedback records",
)
def get_feedback(
    feedback_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> HumanFeedbackResponse:
    return _response(_get_owned_feedback(feedback_id, current_user, db))


@router.patch(
    "/{feedback_id}",
    response_model=HumanFeedbackResponse,
    summary="Update the current user's review decision or notes",
)
def update_feedback(
    feedback_id: int,
    payload: HumanFeedbackUpdate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> HumanFeedbackResponse:
    item = _get_owned_feedback(feedback_id, current_user, db)
    updated = HumanFeedbackRepository(db).update(
        item,
        decision=payload.decision,
        feedback=payload.feedback.strip() if payload.feedback else None,
    )
    _sync_workflow_output_status(updated, db)
    return _response(updated)
