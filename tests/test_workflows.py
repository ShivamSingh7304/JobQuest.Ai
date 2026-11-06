from types import SimpleNamespace

import pytest

from jobquest_ai.human_review.approval import check_approval
from jobquest_ai.resume.resume_tailor import TailoredResume
from jobquest_ai.workflows import (
    ApplicationWorkflowError,
    ResumeWorkflowError,
    run_application_workflow,
    run_resume_workflow,
)
from jobquest_ai.workflows import application_workflow, resume_workflow


class FakeApprovalRepository:
    def __init__(self, feedback=None):
        self.feedback = feedback

    def get_latest_decision_for_output(self, **kwargs):
        return self.feedback


class FakeFeedback:
    def __init__(self, decision, feedback=None):
        self.decision = decision
        self.feedback = feedback


class FakeWorkflowOutputRepository:
    def __init__(self):
        self.calls = []
        self.payload_updates = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(id=42)

    def update_payload_for_user(self, output_id, user_id, payload):
        self.payload_updates.append((output_id, user_id, payload))


def fake_tailored(role: str = "Backend Engineer") -> TailoredResume:
    return TailoredResume(
        target_role=role,
        professional_summary="A factual summary.",
        relevant_skills=["Python"],
        experience_bullets=[],
        project_bullets=[],
        additional_relevant_information=[],
        improvement_suggestions=["Add measurable outcomes if available."],
        changes_made=["Highlighted Python experience."],
        verification_notes=["Verify every claim before use."],
    )


def test_resume_workflow_analyzes_and_tailors_without_mutating_content(monkeypatch):
    original = "Alex Sharma\nPython developer\nBuilt APIs"
    calls = {}

    monkeypatch.setattr(
        resume_workflow,
        "analyze_resume",
        lambda parsed: SimpleNamespace(
            model_dump=lambda: {"skills": ["Python"], "experience": []}
        ),
    )

    def fake_tailor(*, resume, job_description, analysis):
        calls.update(
            resume=resume,
            job_description=job_description,
            analysis=analysis,
        )
        return fake_tailored(job_description)

    monkeypatch.setattr(resume_workflow, "tailor_resume", fake_tailor)

    result = run_resume_workflow(original, "Backend Engineer")

    assert result.status == "awaiting_review"
    assert result.original_content_unchanged is True
    assert calls["resume"] == original
    assert calls["job_description"] == "Backend Engineer"
    assert result.to_dict()["human_review"]["status"] == "pending"


def test_resume_workflow_can_use_existing_file_analysis_tool(monkeypatch):
    monkeypatch.setattr(
        resume_workflow,
        "analyze_uploaded_resume",
        lambda **kwargs: {
            "success": True,
            "analysis": {"skills": ["FastAPI"]},
        },
    )
    monkeypatch.setattr(
        resume_workflow,
        "tailor_resume",
        lambda **kwargs: fake_tailored(kwargs["job_description"]),
    )

    result = run_resume_workflow(
        "Resume text remains the source of truth.",
        "Python API Engineer",
        file_path="resume.pdf",
    )

    assert result.analysis == {"skills": ["FastAPI"]}
    assert result.tailoring.target_role == "Python API Engineer"


def test_resume_workflow_persists_reviewable_output(monkeypatch):
    repository = FakeWorkflowOutputRepository()
    monkeypatch.setattr(
        resume_workflow,
        "analyze_resume",
        lambda parsed: SimpleNamespace(
            model_dump=lambda: {"skills": ["Python"]}
        ),
    )
    monkeypatch.setattr(
        resume_workflow,
        "tailor_resume",
        lambda **kwargs: fake_tailored(kwargs["job_description"]),
    )

    result = run_resume_workflow(
        "Resume text",
        "Backend Engineer",
        user_id=7,
        workflow_output_repository=repository,
        output_key="resume-1-job-1",
    )

    assert result.workflow_output_id == 42
    assert result.status == "awaiting_review"
    assert len(repository.calls) == 1
    assert repository.calls[0]["user_id"] == 7
    assert repository.calls[0]["workflow_name"] == "resume_analysis_and_tailoring"
    assert repository.calls[0]["output_type"] == "resume"
    assert repository.calls[0]["output_key"] == "resume-1-job-1"
    assert repository.calls[0]["status"] == "pending_review"
    assert repository.calls[0]["payload"]["human_review"]["required"] is True
    assert repository.payload_updates[0][0:2] == (42, 7)
    assert repository.payload_updates[0][2]["workflow_output_id"] == 42


@pytest.mark.parametrize(
    "resume_content,target_role",
    [("", "Backend Engineer"), ("Resume", "")],
)
def test_resume_workflow_rejects_missing_inputs(resume_content, target_role):
    with pytest.raises(ValueError):
        run_resume_workflow(resume_content, target_role)


def test_resume_workflow_surfaces_dependency_failures(monkeypatch):
    def fail(_parsed):
        raise RuntimeError("analysis service unavailable")

    monkeypatch.setattr(resume_workflow, "analyze_resume", fail)

    with pytest.raises(ResumeWorkflowError, match="analysis service unavailable"):
        run_resume_workflow("Resume text", "Backend Engineer")


def test_approval_defaults_to_pending():
    result = check_approval()

    assert result.approved is False
    assert result.state == "pending"
    assert "No application was submitted" in result.message


def test_application_workflow_blocks_without_explicit_approval(monkeypatch):
    calls = []

    def fake_prepare(**kwargs):
        calls.append(("prepare", kwargs))
        return "Review resume and job requirements."

    def unexpected_summary(**kwargs):
        calls.append(("summary", kwargs))
        raise AssertionError("status summary must not run before approval")

    monkeypatch.setattr(application_workflow, "prepare_application", fake_prepare)
    monkeypatch.setattr(
        application_workflow,
        "summarize_application_status",
        unexpected_summary,
    )

    result = run_application_workflow(
        "Stripe",
        "Backend Engineer",
        resume_ready=True,
        job_id=4,
        resume_id=2,
    )

    assert result.status == "pending_approval"
    assert result.submission_allowed is False
    assert result.approval.state == "pending"
    assert [call[0] for call in calls] == ["prepare"]


def test_application_workflow_allows_only_approved_follow_up(monkeypatch):
    monkeypatch.setattr(
        application_workflow,
        "prepare_application",
        lambda **kwargs: "Resume: ready",
    )
    monkeypatch.setattr(
        application_workflow,
        "summarize_application_status",
        lambda **kwargs: "Application approved",
    )

    result = run_application_workflow(
        "Stripe",
        "Backend Engineer",
        resume_ready=True,
        user_id=1,
        workflow_output_id="application-1",
        feedback_repository=FakeApprovalRepository(
            FakeFeedback("approve", "Ready to submit.")
        ),
    )

    assert result.status == "approved_for_submission"
    assert result.submission_allowed is True
    assert result.approval.state == "approved"


def test_application_workflow_requires_persisted_approval(monkeypatch):
    monkeypatch.setattr(
        application_workflow,
        "prepare_application",
        lambda **kwargs: "Resume: ready",
    )
    monkeypatch.setattr(
        application_workflow,
        "summarize_application_status",
        lambda **kwargs: pytest.fail("Submission path must remain blocked"),
    )

    result = run_application_workflow(
        "Stripe",
        "Backend Engineer",
        resume_ready=True,
        approved=True,
        user_id=1,
        workflow_output_id="application-1",
        feedback_repository=FakeApprovalRepository(),
    )

    assert result.status == "pending_approval"
    assert result.submission_allowed is False
    assert result.approval.state == "pending"


def test_application_workflow_surfaces_tool_failures(monkeypatch):
    monkeypatch.setattr(
        application_workflow,
        "prepare_application",
        lambda **kwargs: (_ for _ in ()).throw(RuntimeError("checklist failed")),
    )

    with pytest.raises(ApplicationWorkflowError, match="checklist failed"):
        run_application_workflow("Stripe", "Backend Engineer")


@pytest.mark.parametrize("company,role", [("", "Engineer"), ("Stripe", "")])
def test_application_workflow_rejects_missing_inputs(company, role):
    with pytest.raises(ValueError):
        run_application_workflow(company, role)
