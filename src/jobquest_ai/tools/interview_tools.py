"""Interview preparation tools."""

from langchain_core.tools import tool


@tool
def generate_interview_questions(
    role: str,
    topic: str,
    difficulty: str = "beginner",
) -> str:
    """Generate a basic interview practice outline for a role and topic."""

    return (
        f"Interview practice for {role}\n"
        f"Topic: {topic}\n"
        f"Difficulty: {difficulty}\n"
        "Start by reviewing fundamental concepts, then practice "
        "explaining solutions and analyzing their complexity."
    )


@tool
def create_mock_interview_plan(
    role: str,
    interview_type: str = "behavioral",
) -> str:
    """Create a short mock interview practice plan."""

    return (
        f"Mock interview plan for {role}\n"
        f"Interview type: {interview_type}\n"
        "Prepare an introduction, practice role-relevant questions, use "
        "specific examples, and finish with questions for the interviewer."
    )


TOOLS = [generate_interview_questions, create_mock_interview_plan]