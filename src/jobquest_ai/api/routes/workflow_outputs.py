"""Authenticated API for persisted workflow outputs and revisions."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from jobquest_ai.api.schemas import (
    WorkflowOutputCreate,
    WorkflowOutputResponse,
    WorkflowOutputRevisionCreate,
)
from jobquest_ai.auth.dependencies import get_current_user
from jobquest_ai.database.connection import get_db
from jobquest_ai.database.models.user import User
from jobquest_ai.database.repositories.workflow_output_repository import (
    WorkflowOutputRepository,
)

router = APIRouter(prefix="/workflow-outputs", tags=["Workflow outputs"])


def _response(item) -> WorkflowOutputResponse:
    return WorkflowOutputResponse.model_validate(item)


def _get_owned_output(output_id: int, current_user: User, db: Session):
    repo = WorkflowOutputRepository(db)
    item = repo.get_by_id(output_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Workflow output not found.")
    if item.user_id != current_user.id:
        raise HTTPException(
            status_code=403,
            detail="You do not have access to this workflow output.",
        )
    return item


@router.post(
    "",
    response_model=WorkflowOutputResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Persist a workflow output",
)
def create_workflow_output(
    payload: WorkflowOutputCreate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> WorkflowOutputResponse:
    try:
        item = WorkflowOutputRepository(db).create(
            user_id=current_user.id,
            workflow_name=payload.workflow_name,
            output_type=payload.output_type,
            output_key=payload.output_key,
            payload=payload.payload,
            status=payload.status,
            parent_output_id=payload.parent_output_id,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return _response(item)


@router.get("", response_model=list[WorkflowOutputResponse])
def list_workflow_outputs(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    workflow_name: str | None = Query(default=None, min_length=1, max_length=100),
    output_status: str | None = Query(
        default=None, alias="status", min_length=1, max_length=32
    ),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
) -> list[WorkflowOutputResponse]:
    items = WorkflowOutputRepository(db).list_by_user(
        current_user.id,
        workflow_name=workflow_name,
        status=output_status,
        skip=skip,
        limit=limit,
    )
    return [_response(item) for item in items]


@router.get("/{output_id}", response_model=WorkflowOutputResponse)
def get_workflow_output(
    output_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> WorkflowOutputResponse:
    return _response(_get_owned_output(output_id, current_user, db))


@router.post(
    "/{output_id}/revisions",
    response_model=WorkflowOutputResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new revision without overwriting the original",
)
def create_workflow_output_revision(
    output_id: int,
    payload: WorkflowOutputRevisionCreate,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> WorkflowOutputResponse:
    parent = _get_owned_output(output_id, current_user, db)
    item = WorkflowOutputRepository(db).create_revision(
        parent,
        payload=payload.payload,
        status=payload.status,
    )
    return _response(item)
