from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from jobquest_ai.agent.agent_factory import AgentConfigurationError
from jobquest_ai.api.routes import chat as chat_route
from jobquest_ai.auth.dependencies import get_current_user
from jobquest_ai.database.connection import get_db
from jobquest_ai.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def override_auth_and_db():
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(
        id=1,
        is_active=True,
    )
    app.dependency_overrides[get_db] = lambda: object()
    yield
    app.dependency_overrides.clear()


def test_chat_route_returns_assistant_response(monkeypatch):
    class FakeAgent:
        def respond(self, user, message):
            assert user.id == 1
            assert message == "Find jobs in Bangalore"
            return "Here are some jobs for you."

    monkeypatch.setattr(chat_route, "create_career_agent", lambda db: FakeAgent())

    response = client.post("/chat", json={"message": "Find jobs in Bangalore"})

    assert response.status_code == 200
    assert response.json() == {"response": "Here are some jobs for you."}


def test_chat_route_returns_clear_error_when_agent_cannot_configure(monkeypatch):
    def raise_config_error(*, db):
        _ = db
        raise AgentConfigurationError("GROQ_API_KEY is not configured.")

    monkeypatch.setattr(chat_route, "create_career_agent", raise_config_error)

    response = client.post("/chat", json={"message": "Help me prepare for interviews"})

    assert response.status_code == 503
    assert "GROQ_API_KEY" in response.json()["detail"]


def test_chat_route_validates_missing_message():
    response = client.post("/chat", json={})

    assert response.status_code == 422
