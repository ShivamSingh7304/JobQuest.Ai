import pytest
from langchain_core.messages import AIMessage
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from jobquest_ai.agent.career_agent import CareerAgent, CareerAgentError
from jobquest_ai.database.connection import Base
from jobquest_ai.database.models.resume import Resume
from jobquest_ai.database.models.user import User
from jobquest_ai.database.models.user_memory import UserMemory
from jobquest_ai.memory.memory_manager import MemoryManager
from jobquest_ai.memory.user_profile import UserProfile


class FakeAgent:
    def __init__(self):
        self.messages = None

    def invoke(self, payload, config=None):
        assert config["configurable"]["user_id"] == 1
        self.messages = payload["messages"]
        return {"messages": [*self.messages, AIMessage(content="Career advice.")]}


class FakeAgentFactory:
    def __init__(self):
        self.route = None
        self.agent = FakeAgent()

    def create(self, route):
        self.route = route
        return self.agent


class FailingAgent:
    def invoke(self, payload, config=None):
        _ = payload, config
        raise RuntimeError("private provider details")


class FailingAgentFactory:
    def create(self, route):
        _ = route
        return FailingAgent()


class FakeExtractor:
    def __init__(self, profile: UserProfile):
        self.profile = profile

    def extract(self, conversation_text: str) -> UserProfile:
        assert isinstance(conversation_text, str)
        return self.profile


@pytest.fixture
def db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    assert UserMemory.__tablename__ in Base.metadata.tables
    with Session(engine) as session:
        yield session
    engine.dispose()


def create_user(db: Session, email: str) -> User:
    user = User(
        full_name="Test User",
        email=email,
        password_hash="not-a-real-password-hash",
    )
    db.add(user)
    db.flush()
    return user


def test_memory_is_persisted_and_isolated_per_user(db: Session):
    first_user = create_user(db, "first@example.com")
    second_user = create_user(db, "second@example.com")
    manager = MemoryManager(
        db,
        extractor=FakeExtractor(UserProfile(skills=["Python"])),
    )

    manager.update_from_conversation(first_user.id, "I use Python.")

    with Session(db.get_bind()) as new_session:
        persisted_manager = MemoryManager(
            new_session,
            extractor=FakeExtractor(UserProfile()),
        )
        assert persisted_manager.get_profile(first_user.id).skills == ["Python"]

    assert manager.get_profile(second_user.id).skills == []


def test_profile_merges_resume_data_and_extracted_conversation(db: Session):
    user = create_user(db, "candidate@example.com")
    resume = Resume(
        user_id=user.id,
        original_filename="resume.pdf",
        file_path="resume.pdf",
        parsed_data={
            "candidate_summary": "Software engineering student",
            "skills": ["Python"],
            "suggested_roles": ["Backend Developer"],
        },
    )
    db.add(resume)
    db.flush()

    manager = MemoryManager(
        db,
        extractor=FakeExtractor(
            UserProfile(
                career_goals=["Find a backend internship"],
                skills=["FastAPI"],
            )
        ),
    )
    profile = manager.update_from_conversation(
        user.id,
        "I am looking for a backend internship.",
    )

    assert profile.candidate_summary == "Software engineering student"
    assert set(profile.skills) == {"Python", "FastAPI"}
    assert profile.preferred_roles == ["Backend Developer"]
    assert profile.career_goals == ["Find a backend internship"]


def test_career_agent_injects_updated_profile_context(db: Session):
    user = create_user(db, "agent@example.com")
    manager = MemoryManager(
        db,
        extractor=FakeExtractor(UserProfile(skills=["Python"])),
    )
    agent_factory = FakeAgentFactory()
    agent = CareerAgent(
        agent_factory=agent_factory,
        memory_manager=manager,
    )

    answer = agent.respond(user, "I have experience with Python.")

    assert answer == "Career advice."
    assert agent_factory.route.category == "general"
    assert any(
        "Python" in message.content
        for message in agent_factory.agent.messages
        if isinstance(message.content, str)
    )


def test_invalid_profile_data_is_rejected(db: Session):
    user = create_user(db, "invalid@example.com")
    manager = MemoryManager(db, extractor=FakeExtractor(UserProfile()))

    with pytest.raises(ValueError):
        manager.update_profile(user.id, {"skills": "not-a-list"})


def test_career_agent_requires_authenticated_user_object():
    agent = CareerAgent(agent_factory=FakeAgentFactory())

    with pytest.raises(ValueError, match="authenticated user"):
        agent.respond(42, "Help me choose a career")


def test_agent_execution_errors_are_sanitized(db: Session, caplog):
    user = create_user(db, "failure@example.com")
    manager = MemoryManager(
        db,
        extractor=FakeExtractor(UserProfile()),
    )
    agent = CareerAgent(
        agent_factory=FailingAgentFactory(),
        memory_manager=manager,
    )

    with pytest.raises(CareerAgentError) as error:
        agent.respond(user, "Help me choose a career")

    assert "private provider details" not in str(error.value)
    assert "private provider details" not in caplog.text
