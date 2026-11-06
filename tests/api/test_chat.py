"""
Tests for conversation management, message history, and user isolation.

All database and auth interactions are replaced with in-memory fakes so these
tests run without a real database or Groq API key.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from types import SimpleNamespace

# Import app first so load_dotenv() fires before any auth module is resolved.
from jobquest_ai.main import app  # noqa: E402
from jobquest_ai.auth.dependencies import get_current_user
from jobquest_ai.database.connection import get_db

# Remove the startup handler so TestClient never tries to reach the real DB.
app.router.on_startup.clear()


# ---------------------------------------------------------------------------
# In-memory fakes
# ---------------------------------------------------------------------------

class FakeConversation:
    _next_id: int = 1

    def __init__(self, user_id: int, title: str | None = None):
        self.id = FakeConversation._next_id
        FakeConversation._next_id += 1
        self.user_id = user_id
        self.title = title
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        self.created_at = now
        self.updated_at = now


class FakeMessage:
    _next_id: int = 1

    def __init__(self, conversation_id: int, role: str, content: str, position: int):
        self.id = FakeMessage._next_id
        FakeMessage._next_id += 1
        self.conversation_id = conversation_id
        self.role = role
        self.content = content
        self.position = position
        from datetime import datetime, timezone
        self.created_at = datetime.now(timezone.utc)


class FakeConversationRepository:
    def __init__(self, store: dict):
        self._store = store  # shared dict {id: FakeConversation}

    def create(self, user_id: int, title: str | None = None) -> FakeConversation:
        conv = FakeConversation(user_id=user_id, title=title)
        self._store[conv.id] = conv
        return conv

    def get_by_id(self, conversation_id: int) -> FakeConversation | None:
        return self._store.get(conversation_id)

    def list_by_user(
        self, user_id: int, skip: int = 0, limit: int = 50
    ) -> list[FakeConversation]:
        results = [c for c in self._store.values() if c.user_id == user_id]
        results.sort(key=lambda c: c.updated_at, reverse=True)
        return results[skip : skip + limit]

    def update_title(self, conversation: FakeConversation, title: str) -> FakeConversation:
        conversation.title = title
        return conversation

    def delete(self, conversation: FakeConversation) -> None:
        self._store.pop(conversation.id, None)


class FakeConversationMessageRepository:
    def __init__(self, store: dict):
        self._store = store  # shared dict {msg_id: FakeMessage}

    def _next_position(self, conversation_id: int) -> int:
        positions = [
            m.position
            for m in self._store.values()
            if m.conversation_id == conversation_id
        ]
        return 0 if not positions else max(positions) + 1

    def add(self, conversation_id: int, role: str, content: str) -> FakeMessage:
        if role not in {"user", "assistant"}:
            raise ValueError(f"Invalid role '{role}'.")
        if not content or not content.strip():
            raise ValueError("Message content must not be empty.")
        msg = FakeMessage(
            conversation_id=conversation_id,
            role=role,
            content=content.strip(),
            position=self._next_position(conversation_id),
        )
        self._store[msg.id] = msg
        return msg

    def list_by_conversation(
        self, conversation_id: int, skip: int = 0, limit: int = 100
    ) -> list[FakeMessage]:
        results = [
            m for m in self._store.values() if m.conversation_id == conversation_id
        ]
        results.sort(key=lambda m: m.position)
        return results[skip : skip + limit]

    def get_by_id(self, message_id: int) -> FakeMessage | None:
        return self._store.get(message_id)

    def delete(self, message: FakeMessage) -> None:
        self._store.pop(message.id, None)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def make_fake_db(conv_store: dict, msg_store: dict):
    """Return a fake Session-like object; repositories patch themselves in."""
    return SimpleNamespace(_conv=conv_store, _msg=msg_store)


def _patch_repos(monkeypatch, conv_store: dict, msg_store: dict):
    """Monkeypatch repository constructors to use in-memory fakes."""
    import jobquest_ai.api.routes.chat as chat_module

    monkeypatch.setattr(
        chat_module,
        "ConversationRepository",
        lambda db: FakeConversationRepository(conv_store),
    )
    monkeypatch.setattr(
        chat_module,
        "ConversationMessageRepository",
        lambda db: FakeConversationMessageRepository(msg_store),
    )


def make_user(user_id: int = 1):
    return SimpleNamespace(id=user_id, is_active=True)


@pytest.fixture(autouse=True)
def reset_id_counters():
    """Reset fake-object ID counters before each test."""
    FakeConversation._next_id = 1
    FakeMessage._next_id = 1
    yield


@pytest.fixture()
def client_for(monkeypatch):
    """
    Factory: call `client_for(user_id)` to get a TestClient authenticated as
    that user, with fresh in-memory stores. Returns (client, conv_store, msg_store).
    """
    def _factory(user_id: int = 1):
        conv_store: dict = {}
        msg_store: dict = {}

        _patch_repos(monkeypatch, conv_store, msg_store)

        user = make_user(user_id)
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_db] = lambda: make_fake_db(conv_store, msg_store)

        return TestClient(app), conv_store, msg_store

    yield _factory
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Conversation CRUD tests
# ---------------------------------------------------------------------------

class TestCreateConversation:
    def test_creates_conversation_with_title(self, client_for):
        client, conv_store, _ = client_for(user_id=1)
        resp = client.post("/conversations", json={"title": "My first chat"})

        assert resp.status_code == 201
        data = resp.json()
        assert data["title"] == "My first chat"
        assert data["user_id"] == 1
        assert "id" in data
        assert len(conv_store) == 1

    def test_creates_conversation_without_title(self, client_for):
        client, _, _ = client_for()
        resp = client.post("/conversations", json={})

        assert resp.status_code == 201
        assert resp.json()["title"] is None

    def test_title_max_length_enforced(self, client_for):
        client, _, _ = client_for()
        resp = client.post("/conversations", json={"title": "x" * 256})
        assert resp.status_code == 422


class TestListConversations:
    def test_lists_only_own_conversations(self, client_for, monkeypatch):
        client1, conv_store, msg_store = client_for(user_id=1)
        # Seed two conversations for user 1 and one for user 2
        _patch_repos(monkeypatch, conv_store, msg_store)
        client1.post("/conversations", json={"title": "Chat A"})
        client1.post("/conversations", json={"title": "Chat B"})

        # Re-authenticate as user 2 using the same stores
        app.dependency_overrides[get_current_user] = lambda: make_user(2)
        client2 = TestClient(app)
        client2.post("/conversations", json={"title": "Chat C"})

        # Re-authenticate as user 1
        app.dependency_overrides[get_current_user] = lambda: make_user(1)
        client1 = TestClient(app)
        resp = client1.get("/conversations")

        assert resp.status_code == 200
        titles = {c["title"] for c in resp.json()}
        assert "Chat A" in titles
        assert "Chat B" in titles
        assert "Chat C" not in titles

    def test_empty_list_for_new_user(self, client_for):
        client, _, _ = client_for()
        resp = client.get("/conversations")
        assert resp.status_code == 200
        assert resp.json() == []


class TestGetConversation:
    def test_retrieves_own_conversation(self, client_for):
        client, _, _ = client_for()
        create_resp = client.post("/conversations", json={"title": "Details"})
        conv_id = create_resp.json()["id"]

        resp = client.get(f"/conversations/{conv_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == conv_id
        assert data["messages"] == []

    def test_returns_404_for_missing_conversation(self, client_for):
        client, _, _ = client_for()
        resp = client.get("/conversations/99999")
        assert resp.status_code == 404

    def test_returns_403_for_another_users_conversation(
        self, client_for, monkeypatch
    ):
        client1, conv_store, msg_store = client_for(user_id=1)
        create_resp = client1.post("/conversations", json={"title": "Private"})
        conv_id = create_resp.json()["id"]

        # Authenticate as user 2 with the same stores
        _patch_repos(monkeypatch, conv_store, msg_store)
        app.dependency_overrides[get_current_user] = lambda: make_user(2)
        client2 = TestClient(app)

        resp = client2.get(f"/conversations/{conv_id}")
        assert resp.status_code == 403


class TestUpdateConversation:
    def test_updates_title(self, client_for):
        client, _, _ = client_for()
        conv_id = client.post("/conversations", json={"title": "Old"}).json()["id"]

        resp = client.patch(f"/conversations/{conv_id}", json={"title": "New"})
        assert resp.status_code == 200
        assert resp.json()["title"] == "New"

    def test_cannot_update_another_users_conversation(
        self, client_for, monkeypatch
    ):
        client1, conv_store, msg_store = client_for(user_id=1)
        conv_id = client1.post("/conversations", json={"title": "Mine"}).json()["id"]

        _patch_repos(monkeypatch, conv_store, msg_store)
        app.dependency_overrides[get_current_user] = lambda: make_user(2)
        client2 = TestClient(app)

        resp = client2.patch(f"/conversations/{conv_id}", json={"title": "Stolen"})
        assert resp.status_code == 403

    def test_empty_title_rejected(self, client_for):
        client, _, _ = client_for()
        conv_id = client.post("/conversations", json={"title": "A"}).json()["id"]
        resp = client.patch(f"/conversations/{conv_id}", json={"title": ""})
        assert resp.status_code == 422


class TestDeleteConversation:
    def test_deletes_own_conversation(self, client_for):
        client, conv_store, _ = client_for()
        conv_id = client.post("/conversations", json={}).json()["id"]

        resp = client.delete(f"/conversations/{conv_id}")
        assert resp.status_code == 204
        assert conv_id not in conv_store

    def test_cannot_delete_another_users_conversation(
        self, client_for, monkeypatch
    ):
        client1, conv_store, msg_store = client_for(user_id=1)
        conv_id = client1.post("/conversations", json={}).json()["id"]

        _patch_repos(monkeypatch, conv_store, msg_store)
        app.dependency_overrides[get_current_user] = lambda: make_user(2)
        client2 = TestClient(app)

        resp = client2.delete(f"/conversations/{conv_id}")
        assert resp.status_code == 403
        # Conversation still exists
        assert conv_id in conv_store

    def test_returns_404_for_nonexistent_conversation(self, client_for):
        client, _, _ = client_for()
        resp = client.delete("/conversations/99999")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Message tests
# ---------------------------------------------------------------------------

class TestAddMessage:
    def test_appends_user_message(self, client_for):
        client, _, _ = client_for()
        conv_id = client.post("/conversations", json={}).json()["id"]

        resp = client.post(
            f"/conversations/{conv_id}/messages",
            json={"role": "user", "content": "Hello!"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["role"] == "user"
        assert data["content"] == "Hello!"
        assert data["position"] == 0

    def test_appends_assistant_message(self, client_for):
        client, _, _ = client_for()
        conv_id = client.post("/conversations", json={}).json()["id"]

        client.post(
            f"/conversations/{conv_id}/messages",
            json={"role": "user", "content": "Hi"},
        )
        resp = client.post(
            f"/conversations/{conv_id}/messages",
            json={"role": "assistant", "content": "Hello there!"},
        )
        assert resp.status_code == 201
        assert resp.json()["position"] == 1

    def test_invalid_role_rejected(self, client_for):
        client, _, _ = client_for()
        conv_id = client.post("/conversations", json={}).json()["id"]

        resp = client.post(
            f"/conversations/{conv_id}/messages",
            json={"role": "system", "content": "Inject"},
        )
        assert resp.status_code == 422

    def test_empty_content_rejected(self, client_for):
        client, _, _ = client_for()
        conv_id = client.post("/conversations", json={}).json()["id"]

        resp = client.post(
            f"/conversations/{conv_id}/messages",
            json={"role": "user", "content": ""},
        )
        assert resp.status_code == 422

    def test_cannot_add_message_to_another_users_conversation(
        self, client_for, monkeypatch
    ):
        client1, conv_store, msg_store = client_for(user_id=1)
        conv_id = client1.post("/conversations", json={}).json()["id"]

        _patch_repos(monkeypatch, conv_store, msg_store)
        app.dependency_overrides[get_current_user] = lambda: make_user(2)
        client2 = TestClient(app)

        resp = client2.post(
            f"/conversations/{conv_id}/messages",
            json={"role": "user", "content": "Sneaky"},
        )
        assert resp.status_code == 403

    def test_returns_404_for_nonexistent_conversation(self, client_for):
        client, _, _ = client_for()
        resp = client.post(
            "/conversations/99999/messages",
            json={"role": "user", "content": "Hi"},
        )
        assert resp.status_code == 404


class TestListMessages:
    def test_messages_returned_in_order(self, client_for):
        client, _, _ = client_for()
        conv_id = client.post("/conversations", json={}).json()["id"]

        payloads = [
            ("user", "First"),
            ("assistant", "Second"),
            ("user", "Third"),
        ]
        for role, content in payloads:
            client.post(
                f"/conversations/{conv_id}/messages",
                json={"role": role, "content": content},
            )

        resp = client.get(f"/conversations/{conv_id}/messages")
        assert resp.status_code == 200
        messages = resp.json()
        assert len(messages) == 3
        assert [m["content"] for m in messages] == ["First", "Second", "Third"]
        assert [m["position"] for m in messages] == [0, 1, 2]

    def test_get_conversation_embeds_messages(self, client_for):
        client, _, _ = client_for()
        conv_id = client.post("/conversations", json={"title": "With msgs"}).json()["id"]
        client.post(
            f"/conversations/{conv_id}/messages",
            json={"role": "user", "content": "Hey"},
        )

        resp = client.get(f"/conversations/{conv_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["messages"]) == 1
        assert data["messages"][0]["content"] == "Hey"

    def test_cannot_list_messages_of_another_users_conversation(
        self, client_for, monkeypatch
    ):
        client1, conv_store, msg_store = client_for(user_id=1)
        conv_id = client1.post("/conversations", json={}).json()["id"]

        _patch_repos(monkeypatch, conv_store, msg_store)
        app.dependency_overrides[get_current_user] = lambda: make_user(2)
        client2 = TestClient(app)

        resp = client2.get(f"/conversations/{conv_id}/messages")
        assert resp.status_code == 403

    def test_skip_and_limit_pagination(self, client_for):
        client, _, _ = client_for()
        conv_id = client.post("/conversations", json={}).json()["id"]

        for i in range(5):
            client.post(
                f"/conversations/{conv_id}/messages",
                json={"role": "user", "content": f"Message {i}"},
            )

        resp = client.get(f"/conversations/{conv_id}/messages?skip=2&limit=2")
        assert resp.status_code == 200
        messages = resp.json()
        assert len(messages) == 2
        assert messages[0]["content"] == "Message 2"
        assert messages[1]["content"] == "Message 3"
