from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

# Import the application first so its dotenv loading runs before auth imports.
from jobquest_ai.main import app
from jobquest_ai.api.routes import applications as applications_route
from jobquest_ai.auth.dependencies import get_current_user
from jobquest_ai.database.connection import get_db
from jobquest_ai.human_review.approval import ApprovalResult
from jobquest_ai.workflows.application_workflow import ApplicationWorkflowResult


class FakeApplication:
    next_id = 1

    def __init__(self, **data):
        self.id = FakeApplication.next_id
        FakeApplication.next_id += 1
        self.user_id = data["user_id"]
        self.job_id = data["job_id"]
        self.resume_id = data.get("resume_id")
        self.workflow_output_id = data.get("workflow_output_id")
        self.status = data.get("status", "saved")
        self.applied_at = None
        self.notes = data.get("notes")
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = self.created_at


class FakeApplicationRepository:
    store = {}

    def __init__(self, db):
        self.db = db

    def create(self, **data):
        application = FakeApplication(**data)
        self.store[application.id] = application
        return application

    def get_by_id(self, application_id):
        return self.store.get(application_id)

    def list_by_user(self, user_id, status=None, skip=0, limit=50):
        applications = [item for item in self.store.values() if item.user_id == user_id]
        if status:
            applications = [item for item in applications if item.status == status]
        return applications[skip : skip + limit]

    def update_status(self, application, status, notes=None, workflow_output_id=None):
        application.status = status
        if workflow_output_id is not None:
            application.workflow_output_id = workflow_output_id
        if notes is not None:
            application.notes = notes
        if status == "submitted" and application.applied_at is None:
            application.applied_at = datetime.now(timezone.utc)
        application.updated_at = datetime.now(timezone.utc)
        return application

    def delete(self, application):
        self.store.pop(application.id, None)


class FakeJobRepository:
    def __init__(self, db):
        self.db = db

    def get_by_id(self, job_id):
        return (
            SimpleNamespace(
                id=job_id,
                company="Example Co",
                title="Backend Engineer",
                description="Build Python APIs.",
            )
            if job_id == 10
            else None
        )


class FakeResumeRepository:
    def __init__(self, db):
        self.db = db

    def get_by_id(self, resume_id):
        if resume_id == 20:
            return SimpleNamespace(id=20, user_id=1)
        if resume_id == 21:
            return SimpleNamespace(id=21, user_id=2)
        return None


class FakeWorkflowOutputRepository:
    output = SimpleNamespace(
        id=30,
        user_id=1,
        workflow_name="application_preparation",
        status="approved",
    )

    def __init__(self, db):
        self.db = db

    def get_by_id_for_user(self, output_id, user_id):
        if output_id == self.output.id and user_id == self.output.user_id:
            return self.output
        return None


class FakeHumanFeedbackRepository:
    def __init__(self, db):
        self.db = db

    def get_latest_decision_for_output(self, **kwargs):
        if kwargs["workflow_output_id"] == 30 and kwargs["user_id"] == 1:
            return SimpleNamespace(decision="approve", feedback=None)
        return None


@pytest.fixture()
def applications_client(monkeypatch):
    FakeApplication.next_id = 1
    FakeApplicationRepository.store = {}
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=1,
        is_active=True,
    )
    app.dependency_overrides[get_db] = lambda: object()
    monkeypatch.setattr(
        applications_route,
        "ApplicationRepository",
        FakeApplicationRepository,
    )
    monkeypatch.setattr(applications_route, "JobRepository", FakeJobRepository)
    monkeypatch.setattr(
        applications_route,
        "ResumeRepository",
        FakeResumeRepository,
    )
    monkeypatch.setattr(
        applications_route,
        "WorkflowOutputRepository",
        FakeWorkflowOutputRepository,
    )
    monkeypatch.setattr(
        applications_route,
        "HumanFeedbackRepository",
        FakeHumanFeedbackRepository,
    )
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_create_list_update_and_delete_application(applications_client):
    response = applications_client.post(
        "/applications",
        json={"job_id": 10, "resume_id": 20, "notes": "Review requirements"},
    )
    assert response.status_code == 201
    application_id = response.json()["id"]
    assert response.json()["status"] == "saved"

    response = applications_client.get("/applications?status=saved")
    assert response.status_code == 200
    assert len(response.json()) == 1

    response = applications_client.patch(
        f"/applications/{application_id}",
        json={
            "status": "submitted",
            "notes": "Submitted after review",
            "workflow_output_record_id": 30,
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "submitted"
    assert response.json()["applied_at"] is not None

    response = applications_client.delete(f"/applications/{application_id}")
    assert response.status_code == 204
    assert applications_client.get("/applications").json() == []


@pytest.mark.parametrize(
    "payload",
    [
        {"job_id": 0},
        {"job_id": 10, "status": "unknown"},
        {"job_id": 10, "notes": "x" * 32_001},
    ],
)
def test_validates_application_input(applications_client, payload):
    response = applications_client.post("/applications", json=payload)
    assert response.status_code == 422


def test_rejects_missing_job_and_other_users_resume(applications_client):
    response = applications_client.post("/applications", json={"job_id": 999})
    assert response.status_code == 404

    response = applications_client.post(
        "/applications",
        json={"job_id": 10, "resume_id": 21},
    )
    assert response.status_code == 403


def test_user_cannot_access_another_users_application(applications_client):
    application = FakeApplicationRepository(None).create(
        user_id=2,
        job_id=10,
    )

    response = applications_client.get("/applications")
    assert response.status_code == 200
    assert response.json() == []

    response = applications_client.patch(
        f"/applications/{application.id}",
        json={"status": "approved"},
    )
    assert response.status_code == 403

    response = applications_client.delete(f"/applications/{application.id}")
    assert response.status_code == 403


def test_cannot_submit_without_approved_workflow_output(applications_client):
    response = applications_client.post(
        "/applications",
        json={"job_id": 10, "status": "submitted"},
    )
    assert response.status_code == 403


def test_can_submit_with_approved_workflow_output(applications_client):
    response = applications_client.post(
        "/applications",
        json={
            "job_id": 10,
            "resume_id": 20,
            "status": "submitted",
            "workflow_output_record_id": 30,
        },
    )
    assert response.status_code == 201
    assert response.json()["status"] == "submitted"
    assert response.json()["workflow_output_record_id"] == 30


def test_prepare_application_uses_typed_workflow(
    applications_client,
    monkeypatch,
):
    created = applications_client.post(
        "/applications",
        json={"job_id": 10, "resume_id": 20},
    ).json()
    calls = {}

    def fake_workflow(**kwargs):
        calls.update(kwargs)
        return ApplicationWorkflowResult(
            company="Example Co",
            role="Backend Engineer",
            job_id=10,
            resume_id=20,
            job_description="Build Python APIs.",
            workflow_output_id=55,
            status="pending_approval",
            readiness_checklist="Review the API requirements.",
            approval=ApprovalResult(
                approved=False,
                state="pending",
                message="Pending user approval.",
            ),
            next_steps=("Review the checklist.",),
        )

    monkeypatch.setattr(
        applications_route,
        "run_application_workflow",
        fake_workflow,
    )

    response = applications_client.post(
        f"/applications/{created['id']}/prepare"
    )

    assert response.status_code == 200
    assert response.json()["application_id"] == created["id"]
    assert response.json()["workflow_output_id"] == 55
    assert response.json()["readiness_checklist"] == "Review the API requirements."
    assert calls["company"] == "Example Co"
    assert calls["role"] == "Backend Engineer"
    assert calls["user_id"] == 1
    assert calls["output_key"] == f"application-{created['id']}"
