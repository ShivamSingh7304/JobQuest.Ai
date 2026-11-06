from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from jobquest_ai.main import app
from jobquest_ai.api.routes import feedback as feedback_route
from jobquest_ai.auth.dependencies import get_current_user
from jobquest_ai.database.connection import get_db
from jobquest_ai.workflows import application_workflow


class FakeFeedback:
    next_id = 1

    def __init__(self, **data):
        self.id = FakeFeedback.next_id
        FakeFeedback.next_id += 1
        self.user_id = data["user_id"]
        self.decision = data["decision"]
        self.feedback = data.get("feedback")
        self.conversation_id = data.get("conversation_id")
        self.message_id = data.get("message_id")
        self.workflow_name = data.get("workflow_name")
        self.workflow_output_id = data.get("workflow_output_id")
        self.workflow_output_record_id = data.get("workflow_output_record_id")
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = self.created_at


class FakeFeedbackRepository:
    store = {}
    conversations = {10: 1, 11: 2}
    messages = {100: (10, 1), 101: (11, 2)}

    def __init__(self, db):
        self.db = db

    def get_by_id(self, feedback_id):
        return self.store.get(feedback_id)

    def list_by_user(self, user_id, **filters):
        return [
            item
            for item in self.store.values()
            if item.user_id == user_id
            and all(
                value is None or getattr(item, key) == value
                for key, value in filters.items()
            )
        ]

    def get_latest_decision_for_output(
        self, *, user_id, workflow_name, workflow_output_id
    ):
        matches = [
            item
            for item in self.store.values()
            if item.user_id == user_id
            and item.workflow_name == workflow_name
            and item.workflow_output_id == workflow_output_id
        ]
        return matches[-1] if matches else None

    def create(self, **data):
        conversation_id = data.get("conversation_id")
        message_id = data.get("message_id")
        workflow_name = data.get("workflow_name")
        workflow_output_id = data.get("workflow_output_id")
        has_conversation = conversation_id is not None or message_id is not None
        has_workflow = workflow_name is not None or workflow_output_id is not None
        if has_conversation == has_workflow:
            raise ValueError("Provide exactly one feedback target.")
        if message_id is not None:
            message = self.messages.get(message_id)
            if message is None:
                raise LookupError("Conversation message not found.")
            if message[1] != data["user_id"]:
                raise PermissionError("You do not have access to this conversation.")
            if conversation_id is not None and conversation_id != message[0]:
                raise ValueError("message_id does not belong to conversation_id.")
            data["conversation_id"] = message[0]
        if conversation_id is not None:
            owner = self.conversations.get(conversation_id)
            if owner is None:
                raise LookupError("Conversation not found.")
            if owner != data["user_id"]:
                raise PermissionError("You do not have access to this conversation.")
        item = FakeFeedback(**data)
        self.store[item.id] = item
        return item

    def update(self, item, *, decision, feedback):
        item.decision = decision
        item.feedback = feedback
        item.updated_at = datetime.now(timezone.utc)
        return item


@pytest.fixture()
def feedback_client(monkeypatch):
    FakeFeedback.next_id = 1
    FakeFeedbackRepository.store = {}
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=1,
        is_active=True,
    )
    app.dependency_overrides[get_db] = lambda: object()
    monkeypatch.setattr(
        feedback_route,
        "HumanFeedbackRepository",
        FakeFeedbackRepository,
    )
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_approve_workflow_output_is_persisted(feedback_client):
    response = feedback_client.post(
        "/feedback",
        json={
            "decision": "approve",
            "workflow_name": "application_preparation",
            "workflow_output_id": "application-42",
        },
    )

    assert response.status_code == 201
    assert response.json()["decision"] == "approve"
    assert response.json()["user_id"] == 1


def test_request_changes_accepts_optional_feedback(feedback_client):
    response = feedback_client.post(
        "/feedback",
        json={
            "decision": "request_changes",
            "feedback": "Please make the summary more specific.",
            "workflow_name": "resume_analysis_and_tailoring",
            "workflow_output_id": "resume-7",
        },
    )

    assert response.status_code == 201
    assert response.json()["feedback"] == "Please make the summary more specific."


@pytest.mark.parametrize(
    "payload",
    [
        {"decision": "approve"},
        {
            "decision": "approve",
            "conversation_id": 10,
            "workflow_name": "resume",
            "workflow_output_id": "1",
        },
        {
            "decision": "not-a-decision",
            "workflow_name": "resume",
            "workflow_output_id": "1",
        },
    ],
)
def test_feedback_validates_decision_and_target(feedback_client, payload):
    response = feedback_client.post("/feedback", json=payload)
    assert response.status_code == 422


def test_message_feedback_checks_conversation_ownership(feedback_client):
    response = feedback_client.post(
        "/feedback",
        json={"decision": "approve", "message_id": 101},
    )

    assert response.status_code == 403


def test_feedback_is_user_scoped_and_owner_can_update(feedback_client):
    created = feedback_client.post(
        "/feedback",
        json={
            "decision": "request_changes",
            "workflow_name": "resume",
            "workflow_output_id": "resume-1",
        },
    ).json()
    feedback_id = created["id"]

    assert feedback_client.get("/feedback").json()[0]["id"] == feedback_id
    updated = feedback_client.patch(
        f"/feedback/{feedback_id}",
        json={"decision": "approve", "feedback": "Looks good now."},
    )
    assert updated.status_code == 200
    assert updated.json()["decision"] == "approve"

    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=2,
        is_active=True,
    )
    other_user = TestClient(app)
    assert other_user.get(f"/feedback/{feedback_id}").status_code == 403
    assert other_user.patch(
        f"/feedback/{feedback_id}",
        json={"decision": "approve"},
    ).status_code == 403


def test_authenticated_user_can_check_persisted_approval(feedback_client):
    feedback_client.post(
        "/feedback",
        json={
            "decision": "approve",
            "workflow_name": "application_preparation",
            "workflow_output_id": "application-42",
        },
    )

    response = feedback_client.get(
        "/feedback/approval",
        params={
            "workflow_name": "application_preparation",
            "workflow_output_id": "application-42",
        },
    )

    assert response.status_code == 200
    assert response.json()["approved"] is True
    assert response.json()["decision"] == "approve"


def test_missing_and_change_request_approval_stay_blocked(feedback_client):
    missing = feedback_client.get(
        "/feedback/approval",
        params={
            "workflow_name": "application_preparation",
            "workflow_output_id": "missing",
        },
    )
    assert missing.status_code == 200
    assert missing.json()["approved"] is False
    assert missing.json()["state"] == "pending"

    feedback_client.post(
        "/feedback",
        json={
            "decision": "request_changes",
            "feedback": "Fix the summary.",
            "workflow_name": "application_preparation",
            "workflow_output_id": "application-43",
        },
    )
    changed = feedback_client.get(
        "/feedback/approval",
        params={
            "workflow_name": "application_preparation",
            "workflow_output_id": "application-43",
        },
    )
    assert changed.json()["approved"] is False
    assert changed.json()["state"] == "changes_requested"


def test_approval_check_is_user_scoped(feedback_client):
    feedback_client.post(
        "/feedback",
        json={
            "decision": "approve",
            "workflow_name": "application_preparation",
            "workflow_output_id": "private-application",
        },
    )
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=2,
        is_active=True,
    )
    other_user = TestClient(app)
    response = other_user.get(
        "/feedback/approval",
        params={
            "workflow_name": "application_preparation",
            "workflow_output_id": "private-application",
        },
    )

    assert response.status_code == 200
    assert response.json()["approved"] is False
    assert response.json()["state"] == "pending"


def test_request_changes_stays_blocked_in_application_workflow(monkeypatch):
    monkeypatch.setattr(
        application_workflow,
        "prepare_application",
        lambda **kwargs: "Review resume and job requirements.",
    )
    monkeypatch.setattr(
        application_workflow,
        "summarize_application_status",
        lambda **kwargs: pytest.fail("Submission path must remain blocked"),
    )

    result = application_workflow.run_application_workflow(
        "Example Co",
        "Engineer",
        resume_ready=True,
        user_id=1,
        workflow_output_id="application-44",
        feedback_repository=SimpleNamespace(
            get_latest_decision_for_output=lambda **kwargs: SimpleNamespace(
                decision="request_changes",
                feedback="Add more evidence.",
            )
        ),
    )

    assert result.status == "pending_approval"
    assert result.submission_allowed is False
    assert result.approval.state == "changes_requested"
