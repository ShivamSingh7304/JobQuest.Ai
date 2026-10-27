"""Job application tracking and workflow tools."""

from langchain_core.tools import tool


@tool
def prepare_application(
    company: str,
    role: str,
    resume_ready: bool = False,
) -> str:
    """Create an application preparation checklist without submitting it."""

    resume_status = "ready" if resume_ready else "needs review"
    return (
        f"Application checklist for {role} at {company}\n"
        f"Resume: {resume_status}\n"
        "Review the job requirements, tailor application materials, verify "
        "all details, and get the applicant's approval before submission."
    )


@tool
def summarize_application_status(
    company: str,
    role: str,
    status: str,
    next_step: str,
) -> str:
    """Format an application status and its next step."""

    return (
        f"Application: {role} at {company}\n"
        f"Status: {status}\n"
        f"Next step: {next_step}"
    )


TOOLS = [prepare_application, summarize_application_status]