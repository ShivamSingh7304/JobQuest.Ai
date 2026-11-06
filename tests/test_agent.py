from langchain_core.tools import tool

from jobquest_ai.agent.agent_factory import AgentFactory, build_agent
from jobquest_ai.agent.tool_router import ToolRoute, ToolRouter
from jobquest_ai.config.settings import Settings


@tool
def job_tool() -> str:
    """Search jobs."""
    return "jobs"


@tool
def resume_tool() -> str:
    """Review a resume."""
    return "resume"


def test_router_selects_relevant_tool_group_and_prompt():
    router = ToolRouter(
        tool_groups={
            "jobs": [job_tool],
            "resume": [resume_tool],
            "interview": [],
            "application": [],
            "retrieval": [],
        }
    )

    job_route = router.route("Find internships in Delhi")
    general_route = router.route("How can I build confidence?")

    assert job_route.category == "jobs"
    assert router.get_tools(job_route) == [job_tool]
    assert general_route.category == "general"
    assert router.get_tools(general_route) == []


def test_router_covers_feature_categories():
    router = ToolRouter(
        tool_groups={
            "jobs": [job_tool],
            "resume": [resume_tool],
            "interview": [],
            "application": [],
            "retrieval": [],
        }
    )

    assert router.route("Help me update my CV").category == "resume"
    assert router.route("Practice a mock interview").category == "interview"
    assert (
        router.route("How do I follow up on my application?").category
        == "application"
    )
    assert (
        router.route("Recommend some learning resources").category
        == "retrieval"
    )


def test_factory_uses_only_tools_selected_for_route():
    calls = []

    def agent_builder(model, *, tools, system_prompt):
        calls.append((model, tools, system_prompt))
        return object()

    router = ToolRouter(
        tool_groups={
            "jobs": [job_tool],
            "resume": [resume_tool],
            "interview": [],
            "application": [],
            "retrieval": [],
        }
    )
    factory = AgentFactory(
        model=object(),
        tool_router=router,
        agent_builder=agent_builder,
    )

    agent = factory.create(ToolRoute("jobs", "career_coach.md"))
    cached_agent = factory.create(ToolRoute("jobs", "career_coach.md"))

    assert agent is cached_agent
    assert len(calls) == 1
    assert calls[0][1] == [job_tool]
    assert "Career Coach" in calls[0][2]
    assert "JobQuest.Ai" in calls[0][2]


def test_build_agent_supports_model_and_tool_injection():
    calls = []

    def agent_builder(model, *, tools, system_prompt):
        calls.append((model, tools, system_prompt))
        return "agent"

    injected_model = object()
    result = build_agent(
        model=injected_model,
        tools=[],
        agent_builder=agent_builder,
        settings=Settings(groq_api_key=None),
    )

    assert result == "agent"
    assert calls[0][0] is injected_model
    assert calls[0][1] == []
    assert "Job Preparation Specialist" not in calls[0][2]
