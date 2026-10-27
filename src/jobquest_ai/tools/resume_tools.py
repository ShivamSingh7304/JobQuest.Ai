"""Resume analysis and tailoring tools."""

from langchain_core.tools import tool


@tool
def analyze_resume(
    resume_text: str,
    target_role: str,
) -> str:
    """Create a resume review checklist for a target role."""

    return (
        f"Resume review for {target_role}\n"
        f"Resume length: {len(resume_text)} characters\n"
        "Review role-specific skills, measurable achievements, clear "
        "formatting, and relevant keywords."
    )


@tool
def tailor_resume_section(
    section_text: str,
    target_role: str,
) -> str:
    """Suggest how to tailor a resume section to a target role."""

    return (
        f"Resume section tailoring for {target_role}\n"
        f"Current section:\n{section_text}\n"
        "Emphasize relevant accomplishments and skills using concise, "
        "evidence-based wording. Keep all claims accurate."
    )


TOOLS = [analyze_resume, tailor_resume_section]