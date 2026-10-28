from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.tools import BaseTool
from langchain_groq import ChatGroq
from sqlalchemy.orm import Session

from jobquest_ai.agent.career_agent import CareerAgent
from jobquest_ai.agent.tool_router import ToolRoute, ToolRouter
from jobquest_ai.config.settings import Settings, get_settings
from jobquest_ai.memory.memory_manager import MemoryManager

AgentBuilder = Callable[..., Any]
RouteCategoryKey = tuple[str, str]
PROMPT_DIRECTORY = Path(__file__).resolve().parents[1] / "prompts"


class AgentConfigurationError(Exception):
    """Raised when the career agent cannot be configured."""


def _read_prompt(prompt_name: str) -> str:
    if prompt_name == "system.md":
        candidates = ("system.md", "system_prompt.md")
    else:
        candidates = (prompt_name,)

    for candidate in candidates:
        path = PROMPT_DIRECTORY / candidate
        if path.is_file():
            prompt = path.read_text(encoding="utf-8").strip()
            if prompt:
                return prompt

    raise AgentConfigurationError(
        f"Required prompt file is missing or empty: {prompt_name}"
    )


def _system_instructions(task_prompt: str) -> str:
    return "\n\n".join(
        (_read_prompt("system.md"), _read_prompt(task_prompt))
    )


def build_agent(
    model: BaseChatModel | None = None,
    *,
    tools: Sequence[BaseTool] | None = None,
    prompt_name: str = "career_coach.md",
    settings: Settings | None = None,
    agent_builder: AgentBuilder | None = None,
) -> Any:
    """Build a LangChain agent; model, tools, settings, and builder are injectable."""
    config = settings or get_settings()
    if model is None:
        if not config.groq_api_key:
            raise AgentConfigurationError(
                "GROQ_API_KEY is not configured."
            )
        try:
            model = ChatGroq(
                model=config.groq_model,
                temperature=0,
                api_key=config.groq_api_key,
            )
        except Exception as exc:
            raise AgentConfigurationError(
                "Unable to initialize the configured language model."
            ) from exc

    all_tools = (
        list(tools)
        if tools is not None
        else [
            *ToolRouter().get_tools(ToolRoute("jobs", "career_coach.md")),
            *ToolRouter().get_tools(ToolRoute("resume", "career_coach.md")),
            *ToolRouter().get_tools(ToolRoute("interview", "job_prep.md")),
            *ToolRouter().get_tools(
                ToolRoute("application", "career_coach.md")
            ),
            *ToolRouter().get_tools(ToolRoute("retrieval", "career_coach.md")),
        ]
    )
    builder = agent_builder or create_agent
    try:
        return builder(
            model,
            tools=all_tools,
            system_prompt=_system_instructions(prompt_name),
        )
    except Exception as exc:
        raise AgentConfigurationError(
            "Unable to build the LangChain career agent."
        ) from exc


class AgentFactory:
    """Lazily build and cache an agent with only the routed tools."""

    def __init__(
        self,
        model: BaseChatModel,
        *,
        tool_router: ToolRouter | None = None,
        agent_builder: AgentBuilder | None = None,
    ):
        self._model = model
        self._router = tool_router or ToolRouter()
        self._builder = agent_builder or create_agent
        self._agents: dict[RouteCategoryKey, Any] = {}

    def create(self, route: ToolRoute) -> Any:
        cache_key = (route.category, route.prompt_name)
        if cache_key in self._agents:
            return self._agents[cache_key]

        try:
            agent = self._builder(
                self._model,
                tools=self._router.get_tools(route),
                system_prompt=_system_instructions(route.prompt_name),
            )
        except Exception as exc:
            raise AgentConfigurationError(
                "Unable to build the routed career agent."
            ) from exc

        self._agents[cache_key] = agent
        return agent


def create_career_agent(
    db: Session | None = None,
    *,
    model: BaseChatModel | None = None,
    settings: Settings | None = None,
    agent_builder: AgentBuilder | None = None,
) -> CareerAgent:
    """Create the authenticated-user career assistant with persistent memory."""
    config = settings or get_settings()
    if model is None:
        if not config.groq_api_key:
            raise AgentConfigurationError(
                "GROQ_API_KEY is not configured."
            )
        try:
            model = ChatGroq(
                model=config.groq_model,
                temperature=0,
                api_key=config.groq_api_key,
            )
        except Exception as exc:
            raise AgentConfigurationError(
                "Unable to initialize the configured language model."
            ) from exc

    factory = AgentFactory(model, agent_builder=agent_builder)
    return CareerAgent(
        agent_factory=factory,
        memory_manager=MemoryManager(db) if db is not None else None,
    )