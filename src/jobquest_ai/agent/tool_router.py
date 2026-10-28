import re
from dataclasses import dataclass
from typing import Literal

from langchain_core.tools import BaseTool

from jobquest_ai.tools.application_tools import TOOLS as APPLICATION_TOOLS
from jobquest_ai.tools.interview_tools import TOOLS as INTERVIEW_TOOLS
from jobquest_ai.tools.job_tools import TOOLS as JOB_TOOLS
from jobquest_ai.tools.resume_tools import TOOLS as RESUME_TOOLS
from jobquest_ai.tools.retrieval_tools import TOOLS as RETRIEVAL_TOOLS

RouteCategory = Literal[
    "general",
    "jobs",
    "resume",
    "interview",
    "application",
    "retrieval",
]


@dataclass(frozen=True)
class ToolRoute:
    category: RouteCategory
    prompt_name: str


class ToolRouter:
    """Select only the tools and task prompt relevant to a user request."""

    _ROUTES: tuple[tuple[RouteCategory, re.Pattern[str], str], ...] = (
        (
            "application",
            re.compile(
                r"\b(application|applied|follow[\s-]?up|offer status|"
                r"application status)\b",
                re.IGNORECASE,
            ),
            "career_coach.md",
        ),
        (
            "interview",
            re.compile(
                r"\b(interview|mock interview|technical round|"
                r"behavioral round)\b",
                re.IGNORECASE,
            ),
            "job_prep.md",
        ),
        (
            "resume",
            re.compile(r"\b(resume|résumé|cv)\b", re.IGNORECASE),
            "career_coach.md",
        ),
        (
            "jobs",
            re.compile(
                r"\b(job search|find jobs|job openings?|job listings?|"
                r"internships?|job opportunities|match me with jobs)\b",
                re.IGNORECASE,
            ),
            "career_coach.md",
        ),
        (
            "retrieval",
            re.compile(
                r"\b(resources?|courses?|tutorials?|learning materials?)\b",
                re.IGNORECASE,
            ),
            "career_coach.md",
        ),
    )

    def __init__(self, tool_groups: dict[str, list[BaseTool]] | None = None):
        self._tool_groups = tool_groups or {
            "jobs": JOB_TOOLS,
            "resume": RESUME_TOOLS,
            "interview": INTERVIEW_TOOLS,
            "application": APPLICATION_TOOLS,
            "retrieval": RETRIEVAL_TOOLS,
        }

    def route(self, message: str) -> ToolRoute:
        if not isinstance(message, str) or not message.strip():
            raise ValueError("message must be a non-empty string")

        for category, pattern, prompt_name in self._ROUTES:
            if pattern.search(message):
                return ToolRoute(category=category, prompt_name=prompt_name)

        return ToolRoute(category="general", prompt_name="career_coach.md")

    def get_tools(self, route: ToolRoute) -> list[BaseTool]:
        if route.category == "general":
            return []
        return list(self._tool_groups[route.category])