from pathlib import Path
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from jobquest_ai.api.schemas import ResumeResponse, ResumeTailorRequest
from jobquest_ai.auth.dependencies import get_current_user
from jobquest_ai.database.connection import get_db
from jobquest_ai.database.models.user import User
from jobquest_ai.database.repositories.resume_repository import ResumeRepository
from jobquest_ai.resume.resume_analyzer import (
    ResumeAnalysisError,
    analyze_resume,
)
from jobquest_ai.resume.resume_parser import (
    MAX_FILE_SIZE_MB,
    SUPPORTED_EXTENSIONS,
    ResumeParsingError,
    parse_resume,
)
from jobquest_ai.resume.resume_tailor import (
    ResumeTailoringError,
    TailoredResume,
    tailor_resume,
)

router = APIRouter(prefix="/resumes", tags=["Resumes"])
RESUME_STORAGE_DIRECTORY = Path(__file__).resolve().parents[4] / "data" / "resumes"
MAX_UPLOAD_BYTES = MAX_FILE_SIZE_MB * 1024 * 1024


def _resume_response(resume) -> ResumeResponse:
    return ResumeResponse.model_validate(resume)


def _get_owned_resume(resume_id: int, current_user: User, db: Session):
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
    return resume


@router.post(
    "/upload",
    response_model=ResumeResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Upload, parse, and analyze a resume",
)
def upload_resume(
    file: Annotated[UploadFile, File(...)],
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ResumeResponse:
    filename = Path(file.filename or "").name
    suffix = Path(filename).suffix.lower()
    if not filename or suffix not in SUPPORTED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Unsupported file format. Upload a PDF or DOCX file.",
        )

    content = file.file.read(MAX_UPLOAD_BYTES + 1)
    if not content:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="The uploaded resume is empty.",
        )
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Resume exceeds the {MAX_FILE_SIZE_MB} MB limit.",
        )

    user_directory = RESUME_STORAGE_DIRECTORY / str(current_user.id)
    stored_path = user_directory / f"{uuid4().hex}{suffix}"
    stored_path.parent.mkdir(parents=True, exist_ok=True)
    stored_path.write_bytes(content)

    try:
        parsed_resume = parse_resume(stored_path)
        analysis = analyze_resume(parsed_resume)
        analysis_data = analysis.model_dump()
        resume = ResumeRepository(db).create(
            user_id=current_user.id,
            original_filename=filename,
            file_path=str(stored_path),
            extracted_text=parsed_resume["text"],
            parsed_data=analysis_data,
        )
    except ResumeParsingError as exc:
        stored_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except ResumeAnalysisError as exc:
        stored_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Resume analysis failed: {exc}",
        ) from exc
    except Exception:
        stored_path.unlink(missing_ok=True)
        raise

    return _resume_response(resume)


@router.get(
    "",
    response_model=list[ResumeResponse],
    summary="List the current user's resumes",
)
def list_resumes(
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
    skip: int = 0,
    limit: int = 50,
) -> list[ResumeResponse]:
    if skip < 0 or limit < 1 or limit > 100:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="skip must be non-negative and limit must be between 1 and 100.",
        )
    resumes = ResumeRepository(db).list_by_user(
        user_id=current_user.id,
        skip=skip,
        limit=limit,
    )
    return [_resume_response(resume) for resume in resumes]


@router.get(
    "/{resume_id}",
    response_model=ResumeResponse,
    summary="Retrieve one of the current user's resumes",
)
def get_resume(
    resume_id: int,
    db: Annotated[Session, Depends(get_db)],
    current_user: Annotated[User, Depends(get_current_user)],
) -> ResumeResponse:
    return _resume_response(_get_owned_resume(resume_id, current_user, db))


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
    resume = _get_owned_resume(resume_id, current_user, db)

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
