"""Authenticated interview question generation and mock interview endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from jobquest_ai.api.schemas import (
    InterviewAnswerRequest,
    InterviewGenerateRequest,
    InterviewReportResponse,
    InterviewStartResponse,
    InterviewTurnResponse,
)
from jobquest_ai.auth.dependencies import get_current_user
from jobquest_ai.database.connection import get_db
from jobquest_ai.database.models.user import User
from jobquest_ai.database.repositories.resume_repository import ResumeRepository
from jobquest_ai.database.repositories.workflow_output_repository import (
    WorkflowOutputRepository,
)
from jobquest_ai.interview.mock_interview import (
    MockInterviewError,
    MockInterviewSession,
    generate_interview_report,
    start_interview,
    submit_answer,
)
from jobquest_ai.interview.question_generator import (
    QuestionGenerationError,
    generate_interview_questions,
)

router = APIRouter(prefix="/interviews", tags=["Interviews"])


def _get_owned_resume(resume_id: int, current_user: User, db: Session):
    resume = ResumeRepository(db).get_by_id(resume_id)
    if resume is None:
        raise HTTPException(status_code=404, detail="Resume not found.")
    if resume.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="You do not have access to this resume.")
    if not isinstance(resume.extracted_text, str) or not resume.extracted_text.strip():
        raise HTTPException(status_code=422, detail="Resume does not contain readable text.")
    return resume


def _get_session(session_id: str, current_user: User, db: Session):
    output = WorkflowOutputRepository(db).get_by_key_for_user(
        user_id=current_user.id,
        workflow_name="mock_interview",
        output_key=session_id,
    )
    if output is None:
        raise HTTPException(status_code=404, detail="Interview session not found.")
    return output


@router.post(
    "/questions",
    response_model=InterviewStartResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate questions and start a mock interview",
)
def generate_questions_and_start(
    payload: InterviewGenerateRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> InterviewStartResponse:
    resume = _get_owned_resume(payload.resume_id, current_user, db)
    try:
        question_set = generate_interview_questions(
            target_role=payload.target_role,
            job_description=payload.job_description,
            resume_text=resume.extracted_text,
            question_count=payload.question_count,
            categories=payload.categories,
            difficulty=payload.difficulty,
        )
        session, first_question = start_interview(question_set)
    except (QuestionGenerationError, MockInterviewError) as exc:
        raise HTTPException(status_code=502, detail=f"Interview generation failed: {exc}") from exc

    output = WorkflowOutputRepository(db).create(
        user_id=current_user.id,
        workflow_name="mock_interview",
        output_type="interview_session",
        output_key=session.session_id,
        payload={
            "session": session.model_dump(mode="json"),
            "resume_id": resume.id,
            "job_description": payload.job_description,
        },
        status="in_progress",
    )
    return InterviewStartResponse(
        session_id=session.session_id,
        workflow_output_id=output.id,
        target_role=session.target_role,
        status=session.status,
        question=first_question.model_dump(),
    )


@router.post(
    "/{session_id}/answer",
    response_model=InterviewTurnResponse,
    summary="Evaluate an answer and advance the mock interview",
)
def answer_interview_question(
    session_id: str,
    payload: InterviewAnswerRequest,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> InterviewTurnResponse:
    output = _get_session(session_id, current_user, db)
    session_data = output.payload.get("session")
    if not isinstance(session_data, dict):
        raise HTTPException(status_code=500, detail="Interview session data is invalid.")
    try:
        session = MockInterviewSession.model_validate(session_data)
        result = submit_answer(session, payload.answer)
    except MockInterviewError as exc:
        raise HTTPException(status_code=502, detail=f"Interview evaluation failed: {exc}") from exc

    output.payload = {**output.payload, "session": session.model_dump(mode="json")}
    output.status = "completed" if result.interview_completed else "in_progress"
    db.commit()
    db.refresh(output)
    return InterviewTurnResponse(
        session_id=session.session_id,
        evaluation=result.evaluation.model_dump(),
        next_question=(result.next_question.model_dump() if result.next_question else None),
        interview_completed=result.interview_completed,
        answered_questions=result.answered_questions,
        total_questions=result.total_questions,
    )


@router.get(
    "/{session_id}/report",
    response_model=InterviewReportResponse,
    summary="Get the completed mock interview report",
)
def get_interview_report(
    session_id: str,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> InterviewReportResponse:
    output = _get_session(session_id, current_user, db)
    try:
        session = MockInterviewSession.model_validate(output.payload.get("session"))
        report = generate_interview_report(session)
    except (MockInterviewError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return InterviewReportResponse(report=report.model_dump(mode="json"))
