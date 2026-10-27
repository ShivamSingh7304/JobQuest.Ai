"""Job search and job-matching tools."""

from langchain_core.tools import tool


@tool
def search_jobs(
    role: str,
    location: str = "any location",
    work_mode: str = "any",
) -> str:
    """Create a job-search brief for a role, location, and work mode."""

    return (
        f"Job search brief for {role}\n"
        f"Location: {location}\n"
        f"Work mode: {work_mode}\n"
        "Connect a job-board provider to retrieve matching openings."
    )


@tool
def match_job_to_skills(
    job_title: str,
    skills: str,
) -> str:
    """Prepare a job-match summary from a title and candidate skills."""

    return (
        f"Job match preparation for {job_title}\n"
        f"Candidate skills: {skills}\n"
        "Compare these skills with the job description to identify matches "
        "and gaps."
    )


TOOLS = [search_jobs, match_job_to_skills]