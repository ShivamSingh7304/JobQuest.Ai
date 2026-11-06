from datetime import datetime, timezone
from pathlib import Path
import shutil
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

# Import the application first so its dotenv loading runs before auth imports.
from jobquest_ai.main import app
from jobquest_ai.api.routes import resumes as resumes_route
from jobquest_ai.auth.dependencies import get_current_user
from jobquest_ai.database.connection import get_db
from jobquest_ai.resume.resume_tailor import TailoredResume
from jobquest_ai.workflows.resume_workflow import (
    ResumeWorkflowError,
    ResumeWorkflowResult,
)


class FakeResumeRepository:
    resumes = {}
    next_id = 10

    def __init__(self, db):
        self.db = db

    def get_by_id(self, resume_id):
        return self.resumes.get(resume_id)

    def create(self, **data):
        resume = SimpleNamespace(
            id=FakeResumeRepository.next_id,
            user_id=data["user_id"],
            original_filename=data["original_filename"],
            file_path=data["file_path"],
            extracted_text=data["extracted_text"],
            parsed_data=data["parsed_data"],
            version=1,
            created_at=datetime.now(timezone.utc),
        )
        FakeResumeRepository.next_id += 1
        self.resumes[resume.id] = resume
        return resume

    def list_by_user(self, user_id, skip=0, limit=50):
        resumes = [resume for resume in self.resumes.values() if resume.user_id == user_id]
        return resumes[skip : skip + limit]


@pytest.fixture()
def resume_client(monkeypatch):
    FakeResumeRepository.resumes = {
        1: SimpleNamespace(
            id=1,
            user_id=1,
            original_filename="resume.pdf",
            file_path="resume.pdf",
            extracted_text="Python developer with FastAPI experience.",
            parsed_data={"candidate_summary": "Python developer"},
            version=1,
            created_at=datetime.now(timezone.utc),
        ),
        2: SimpleNamespace(
            id=2,
            user_id=2,
            original_filename="private.pdf",
            file_path="private.pdf",
            extracted_text="Private resume text.",
            parsed_data={"candidate_summary": "Private"},
            version=1,
            created_at=datetime.now(timezone.utc),
        ),
        3: SimpleNamespace(
            id=3,
            user_id=1,
            original_filename="empty.pdf",
            file_path="empty.pdf",
            extracted_text="   ",
            parsed_data=None,
            version=1,
            created_at=datetime.now(timezone.utc),
        ),
        4: SimpleNamespace(
            id=4,
            user_id=2,
            original_filename="private.pdf",
            extracted_text="Private resume text.",
            parsed_data={"candidate_summary": "Private"},
            version=1,
            created_at=datetime.now(timezone.utc),
        ),
    }
    FakeResumeRepository.next_id = 10
    user = SimpleNamespace(id=1, is_active=True)
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_db] = lambda: object()
    monkeypatch.setattr(resumes_route, "ResumeRepository", FakeResumeRepository)
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture()
def resume_storage(monkeypatch):
    storage = Path("data/.resume-upload-test-storage")
    shutil.rmtree(storage, ignore_errors=True)
    monkeypatch.setattr(resumes_route, "RESUME_STORAGE_DIRECTORY", storage)
    yield storage
    shutil.rmtree(storage, ignore_errors=True)


def test_tailors_users_own_resume(resume_client, monkeypatch):
    result = TailoredResume(
        target_role="Python Developer",
        professional_summary="Python developer with API experience.",
        relevant_skills=["Python", "FastAPI"],
        experience_bullets=[],
        project_bullets=[],
        additional_relevant_information=[],
        improvement_suggestions=[],
        changes_made=["Focused the summary on API experience."],
        verification_notes=[],
    )
    calls = {}

    def fake_run_resume_workflow(**kwargs):
        calls.update(kwargs)
        return ResumeWorkflowResult(
            target_role=kwargs["target_role"],
            analysis={"skills": ["Python"]},
            tailoring=result,
            workflow_output_id=42,
        )

    monkeypatch.setattr(resumes_route, "run_resume_workflow", fake_run_resume_workflow)

    response = resume_client.post(
        "/resumes/1/tailor",
        json={"job_description": "Build Python APIs with FastAPI."},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["workflow"] == "resume_analysis_and_tailoring"
    assert data["workflow_output_id"] == 42
    assert data["tailoring"] == result.model_dump()
    assert calls["resume_content"] == "Python developer with FastAPI experience."
    assert calls["target_role"] == "Build Python APIs with FastAPI."
    assert calls["user_id"] == 1
    assert calls["output_key"].startswith("resume-1-")


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"job_description": ""},
        {"job_description": "x" * 15_001},
    ],
)
def test_rejects_invalid_job_description(resume_client, payload):
    response = resume_client.post("/resumes/1/tailor", json=payload)

    assert response.status_code == 422


def test_rejects_resume_without_readable_text(resume_client, monkeypatch):
    monkeypatch.setattr(
        resumes_route,
        "run_resume_workflow",
        lambda **kwargs: pytest.fail("run_resume_workflow should not be called"),
    )

    response = resume_client.post(
        "/resumes/3/tailor",
        json={"job_description": "Python developer"},
    )

    assert response.status_code == 422
    assert "readable text" in response.json()["detail"]


def test_returns_model_failure_as_gateway_error(resume_client, monkeypatch):
    def fail(**kwargs):
        raise ResumeWorkflowError("model unavailable")

    monkeypatch.setattr(resumes_route, "run_resume_workflow", fail)

    response = resume_client.post(
        "/resumes/1/tailor",
        json={"job_description": "Python developer"},
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "Resume workflow failed: model unavailable"


def test_cannot_tailor_another_users_resume(resume_client, monkeypatch):
    monkeypatch.setattr(
        resumes_route,
        "run_resume_workflow",
        lambda **kwargs: pytest.fail("tailor_resume should not be called"),
    )

    response = resume_client.post(
        "/resumes/2/tailor",
        json={"job_description": "Python developer"},
    )

    assert response.status_code == 403
    assert "access" in response.json()["detail"]


@pytest.mark.parametrize("filename", ["resume.pdf", "resume.docx"])
def test_uploads_and_analyzes_supported_resume(
    resume_client,
    monkeypatch,
    resume_storage,
    filename,
):
    monkeypatch.setattr(
        resumes_route,
        "parse_resume",
        lambda path: {
            "file_name": filename,
            "file_type": filename.rsplit(".", 1)[1],
            "text": "Python developer with API experience.",
            "character_count": 37,
        },
    )
    monkeypatch.setattr(
        resumes_route,
        "analyze_resume",
        lambda parsed: SimpleNamespace(
            model_dump=lambda: {
                "candidate_summary": "Python developer",
                "skills": ["Python"],
            }
        ),
    )

    response = resume_client.post(
        "/resumes/upload",
        files={"file": (filename, b"resume content", "application/octet-stream")},
    )

    assert response.status_code == 201
    data = response.json()
    assert data["original_filename"] == filename
    assert data["extracted_text"] == "Python developer with API experience."
    assert data["parsed_data"]["skills"] == ["Python"]


@pytest.mark.parametrize(
    "filename,content",
    [
        ("resume.txt", b"plain text"),
        ("resume.pdf", b""),
    ],
)
def test_rejects_invalid_resume_upload(resume_client, filename, content):
    response = resume_client.post(
        "/resumes/upload",
        files={"file": (filename, content, "application/octet-stream")},
    )

    assert response.status_code == 422


def test_rejects_oversized_resume_upload(resume_client, monkeypatch):
    monkeypatch.setattr(resumes_route, "MAX_UPLOAD_BYTES", 3)

    response = resume_client.post(
        "/resumes/upload",
        files={"file": ("resume.pdf", b"1234", "application/pdf")},
    )

    assert response.status_code == 413


def test_returns_analysis_failure_as_gateway_error(
    resume_client,
    monkeypatch,
    resume_storage,
):
    monkeypatch.setattr(
        resumes_route,
        "parse_resume",
        lambda path: {"text": "Python developer"},
    )
    monkeypatch.setattr(
        resumes_route,
        "analyze_resume",
        lambda parsed: (_ for _ in ()).throw(
            resumes_route.ResumeAnalysisError("model unavailable")
        ),
    )

    response = resume_client.post(
        "/resumes/upload",
        files={"file": ("resume.pdf", b"resume", "application/pdf")},
    )

    assert response.status_code == 502
    assert "model unavailable" in response.json()["detail"]


def test_lists_and_retrieves_only_owned_resumes(resume_client):
    response = resume_client.get("/resumes")
    assert response.status_code == 200
    assert {item["id"] for item in response.json()} == {1, 3}

    response = resume_client.get("/resumes/4")
    assert response.status_code == 403
