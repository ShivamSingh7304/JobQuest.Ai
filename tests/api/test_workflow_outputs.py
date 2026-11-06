from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from jobquest_ai.main import app
from jobquest_ai.api.routes import workflow_outputs as output_route
from jobquest_ai.auth.dependencies import get_current_user
from jobquest_ai.database.connection import Base, get_db
from jobquest_ai.database.models.user import User
from jobquest_ai.database.repositories.human_feedback_repository import (
    HumanFeedbackRepository,
)
from jobquest_ai.database.repositories.workflow_output_repository import (
    WorkflowOutputRepository,
)


class FakeOutput:
    next_id = 1

    def __init__(self, **data):
        self.id = FakeOutput.next_id
        FakeOutput.next_id += 1
        self.user_id = data["user_id"]
        self.workflow_name = data["workflow_name"]
        self.output_type = data["output_type"]
        self.output_key = data.get("output_key")
        self.payload = data["payload"]
        self.status = data.get("status", "pending_review")
        self.version = data.get("version", 1)
        self.parent_output_id = data.get("parent_output_id")
        self.created_at = datetime.now(timezone.utc)
        self.updated_at = self.created_at


class FakeOutputRepository:
    store = {}

    def __init__(self, db):
        self.db = db

    def get_by_id(self, output_id):
        return self.store.get(output_id)

    def list_by_user(self, user_id, **filters):
        return [
            item for item in self.store.values()
            if item.user_id == user_id
            and (filters.get("workflow_name") is None or item.workflow_name == filters["workflow_name"])
        ]

    def create(self, **data):
        if data.get("parent_output_id") is not None:
            parent = self.store.get(data["parent_output_id"])
            if parent is None or parent.user_id != data["user_id"]:
                raise PermissionError("You do not have access to the parent workflow output.")
            data["version"] = parent.version + 1
        item = FakeOutput(**data)
        self.store[item.id] = item
        return item

    def create_revision(self, parent, *, payload, status):
        parent.status = "superseded"
        return self.create(
            user_id=parent.user_id,
            workflow_name=parent.workflow_name,
            output_type=parent.output_type,
            output_key=parent.output_key,
            payload=payload,
            status=status,
            parent_output_id=parent.id,
        )


@pytest.fixture()
def output_client(monkeypatch):
    FakeOutput.next_id = 1
    FakeOutputRepository.store = {}
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=1,
        is_active=True,
    )
    app.dependency_overrides[get_db] = lambda: object()
    monkeypatch.setattr(output_route, "WorkflowOutputRepository", FakeOutputRepository)
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_workflow_output_is_persisted_and_retrievable(output_client):
    created = output_client.post(
        "/workflow-outputs",
        json={
            "workflow_name": "resume_analysis_and_tailoring",
            "output_type": "resume",
            "output_key": "resume-1",
            "payload": {"target_role": "Backend Engineer"},
        },
    )
    assert created.status_code == 201
    output_id = created.json()["id"]
    assert output_client.get(f"/workflow-outputs/{output_id}").json()["payload"] == {
        "target_role": "Backend Engineer"
    }


def test_workflow_output_revisions_preserve_parent(output_client):
    parent = output_client.post(
        "/workflow-outputs",
        json={
            "workflow_name": "application_preparation",
            "output_type": "application",
            "payload": {"role": "Engineer"},
        },
    ).json()
    revision = output_client.post(
        f"/workflow-outputs/{parent['id']}/revisions",
        json={"payload": {"role": "Senior Engineer"}},
    )

    assert revision.status_code == 201
    assert revision.json()["parent_output_id"] == parent["id"]
    assert revision.json()["version"] == 2
    assert FakeOutputRepository.store[parent["id"]].status == "superseded"


def test_workflow_output_is_user_scoped(output_client):
    created = output_client.post(
        "/workflow-outputs",
        json={
            "workflow_name": "application_preparation",
            "output_type": "application",
            "payload": {"role": "Engineer"},
        },
    ).json()
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=2,
        is_active=True,
    )
    other_user = TestClient(app)

    assert other_user.get(f"/workflow-outputs/{created['id']}").status_code == 403
    assert other_user.post(
        f"/workflow-outputs/{created['id']}/revisions",
        json={"payload": {"role": "Private"}},
    ).status_code == 403


def test_feedback_repository_links_to_owned_workflow_output():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        user = User(
            full_name="Workflow User",
            email="workflow@example.com",
            password_hash="hash",
        )
        db.add(user)
        db.flush()
        output = WorkflowOutputRepository(db).create(
            user_id=user.id,
            workflow_name="application_preparation",
            output_type="application",
            payload={"role": "Engineer"},
        )
        feedback = HumanFeedbackRepository(db).create(
            user_id=user.id,
            decision="approve",
            workflow_output_record_id=output.id,
        )

        assert feedback.workflow_output_record_id == output.id
        assert feedback.workflow_name == output.workflow_name
        assert HumanFeedbackRepository(db).get_latest_decision_for_output(
            user_id=user.id,
            workflow_name=output.workflow_name,
            workflow_output_id=output.id,
        ).decision == "approve"
    engine.dispose()
