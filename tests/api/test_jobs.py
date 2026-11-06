from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

# Import the application first so its dotenv loading runs before auth imports.
from jobquest_ai.main import app
from jobquest_ai.api.routes import jobs as jobs_route
from jobquest_ai.auth.dependencies import get_current_user
from jobquest_ai.database.connection import get_db
from jobquest_ai.jobs.job_service import JobServiceError


class FakeResumeRepository:
    resumes = {}

    def __init__(self, db):
        self.db = db

    def get_by_id(self, resume_id):
        return self.resumes.get(resume_id)


class FakeJobService:
    result = {
        "query": "python developer",
        "country": "India",
        "total_count": 2,
        "pages_fetched": 1,
        "fetched_job_count": 2,
        "rejected_job_count": 0,
        "matched_job_count": 2,
        "match_score_type": "Relative ranking score, not hiring probability",
        "jobs": [
            {
                "external_id": "job-1",
                "title": "Python Developer",
                "company_name": "Example Co",
                "application_url": "https://example.com/jobs/1",
                "match_score": 91.5,
                "match_rank": 1,
                "match_reasons": ["Other candidate skills mentioned: Python"],
            }
        ],
    }
    calls = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False

    def search_and_match(self, **kwargs):
        self.calls.append(kwargs)
        return self.result


class FakeJobRepository:
    jobs = {}
    next_id = 1

    def __init__(self, db):
        self.db = db

    def upsert_external_job(self, **data):
        key = (data["source"], data["external_job_id"])
        job = self.jobs.get(key)
        if job is None:
            job = SimpleNamespace(id=self.next_id)
            self.next_id += 1
            self.jobs[key] = job
        for key, value in data.items():
            setattr(job, key, value)
        return job


@pytest.fixture()
def jobs_client(monkeypatch):
    FakeResumeRepository.resumes = {
        1: SimpleNamespace(
            id=1,
            user_id=1,
            parsed_data={"skills": ["Python"], "preferred_roles": ["Developer"]},
        ),
        2: SimpleNamespace(
            id=2,
            user_id=2,
            parsed_data={"skills": ["Python"]},
        ),
        3: SimpleNamespace(id=3, user_id=1, parsed_data=None),
    }
    FakeJobService.calls = []
    FakeJobRepository.jobs = {}
    FakeJobRepository.next_id = 1
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=1,
        is_active=True,
    )
    app.dependency_overrides[get_db] = lambda: object()
    monkeypatch.setattr(jobs_route, "ResumeRepository", FakeResumeRepository)
    monkeypatch.setattr(jobs_route, "JobService", FakeJobService)
    monkeypatch.setattr(jobs_route, "JobRepository", FakeJobRepository)
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_returns_ranked_jobs_for_users_resume(jobs_client):
    response = jobs_client.post(
        "/jobs/match",
        json={
            "resume_id": 1,
            "query": "python developer",
            "country": "India",
            "limit": 5,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["jobs"][0]["match_score"] == 91.5
    assert "not hiring probability" in data["match_score_type"]
    assert FakeJobService.calls[0]["top_k"] == 5
    assert FakeJobService.calls[0]["candidate_profile"]["skills"] == ["Python"]


@pytest.mark.parametrize(
    "payload",
    [
        {"resume_id": 1, "query": ""},
        {"resume_id": 1, "query": "python", "country": ""},
        {"resume_id": 1, "query": "python", "limit": 0},
        {"resume_id": 0, "query": "python"},
        {"resume_id": 1, "query": "x" * 201},
    ],
)
def test_validates_job_search_input(jobs_client, payload):
    response = jobs_client.post("/jobs/match", json=payload)

    assert response.status_code == 422


def test_rejects_resume_without_usable_profile(jobs_client, monkeypatch):
    monkeypatch.setattr(
        jobs_route,
        "JobService",
        lambda: pytest.fail("JobService should not be created"),
    )

    response = jobs_client.post(
        "/jobs/match",
        json={"resume_id": 3, "query": "python developer"},
    )

    assert response.status_code == 422
    assert "usable profile" in response.json()["detail"]


def test_returns_search_failure_as_gateway_error(jobs_client, monkeypatch):
    class FailingService(FakeJobService):
        def search_and_match(self, **kwargs):
            raise JobServiceError("Himalayas request timed out")

    monkeypatch.setattr(jobs_route, "JobService", FailingService)

    response = jobs_client.post(
        "/jobs/match",
        json={"resume_id": 1, "query": "python developer"},
    )

    assert response.status_code == 502
    assert "timed out" in response.json()["detail"]


def test_cannot_search_using_another_users_resume(jobs_client, monkeypatch):
    monkeypatch.setattr(
        jobs_route,
        "JobService",
        lambda: pytest.fail("JobService should not be created"),
    )

    response = jobs_client.post(
        "/jobs/match",
        json={"resume_id": 2, "query": "python developer"},
    )

    assert response.status_code == 403
    assert "access" in response.json()["detail"]


def test_saves_only_selected_job_and_returns_internal_id(jobs_client):
    payload = {
        "external_id": "himalayas-job-123",
        "title": "Python Developer",
        "company_name": "Example Company",
        "application_url": "https://example.com/jobs/123",
        "description": "Build Python APIs.",
        "location_restrictions": ["India"],
        "employment_type": "Full-time",
        "seniority": "Entry level",
        "published_at": "2026-10-28T10:00:00Z",
    }

    response = jobs_client.post("/jobs/save", json=payload)

    assert response.status_code == 201
    data = response.json()
    assert data["job_id"] == 1
    assert data["external_job_id"] == "himalayas-job-123"
    assert data["company"] == "Example Company"
    assert data["location"] == "India"
    assert len(FakeJobRepository.jobs) == 1


def test_saving_same_external_job_upserts_without_duplicates(jobs_client):
    payload = {
        "external_id": "himalayas-job-123",
        "title": "Python Developer",
        "company_name": "Example Company",
        "application_url": "https://example.com/jobs/123",
    }

    first = jobs_client.post("/jobs/save", json=payload)
    second = jobs_client.post(
        "/jobs/save",
        json={**payload, "title": "Senior Python Developer"},
    )

    assert first.status_code == 201
    assert second.status_code == 201
    assert second.json()["job_id"] == first.json()["job_id"]
    assert second.json()["title"] == "Senior Python Developer"
    assert len(FakeJobRepository.jobs) == 1


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"external_id": "id", "title": "", "company_name": "Company", "application_url": "https://example.com"},
        {"external_id": "id", "title": "Role", "company_name": "Company", "application_url": "not-a-url"},
        {"external_id": "id", "title": "Role", "company_name": "Company", "application_url": "https://example.com", "published_at": "not-a-date"},
    ],
)
def test_validates_selected_job_payload(jobs_client, payload):
    response = jobs_client.post("/jobs/save", json=payload)
    assert response.status_code == 422


def test_returns_clear_error_when_job_persistence_fails(jobs_client, monkeypatch):
    class FailingRepository:
        def __init__(self, db):
            self.db = db

        def upsert_external_job(self, **data):
            raise RuntimeError("database unavailable")

    monkeypatch.setattr(jobs_route, "JobRepository", FailingRepository)
    response = jobs_client.post(
        "/jobs/save",
        json={
            "external_id": "job-1",
            "title": "Python Developer",
            "company_name": "Example Company",
            "application_url": "https://example.com/jobs/1",
        },
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "Unable to save the selected job."
