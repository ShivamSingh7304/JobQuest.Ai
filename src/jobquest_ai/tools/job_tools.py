
"""Job search and job-matching tools."""

import json
from typing import Any

from langchain_core.tools import tool

from jobquest_ai.jobs.job_service import JobService, JobServiceError


def _format_result(result: dict[str, Any]) -> str:
    """Serialize service results into JSON for the agent."""
    return json.dumps(result, ensure_ascii=False, default=str)


@tool
def search_jobs(
    role: str,
    location: str = "India",
    work_mode: str = "any",
    max_pages: int = 2,
    top_k: int = 10,
) -> str:
    """Search real job listings for a role and return ranked results.

    Use this tool when a user wants to find jobs. The role is used as
    the search query. Location is passed as the country filter supported
    by the current job provider. Work mode is currently a user preference
    and is not independently filtered by the provider.
    """

    if not isinstance(role, str) or not role.strip():
        return json.dumps({"error": "role must be a non-empty string"})

    if not isinstance(location, str) or not location.strip():
        return json.dumps({"error": "location must be a non-empty string"})

    if not isinstance(work_mode, str) or not work_mode.strip():
        return json.dumps({"error": "work_mode must be a non-empty string"})

    try:
        # This tool performs job discovery. An empty profile means no
        # candidate-specific ranking should be implied.
        with JobService() as service:
            search_result = service.job_search.search_multiple_pages(
                query=role.strip(),
                country=location.strip(),
                max_pages=max_pages,
            )

        jobs = search_result["jobs"][:top_k]

        return _format_result({
            "query": search_result["query"],
            "country": location.strip(),
            "work_mode_requested": work_mode.strip(),
            "work_mode_filter_applied": False,
            "total_count": search_result["total_count"],
            "pages_fetched": search_result["pages_fetched"],
            "fetched_job_count": search_result["returned_count"],
            "rejected_job_count": search_result["rejected_count"],
            "returned_job_count": len(jobs),
            "jobs": jobs,
        })

    except (JobServiceError, ValueError) as error:
        return json.dumps({"error": str(error)}, ensure_ascii=False)
    except Exception:
        return json.dumps({
            "error": "An unexpected error occurred while searching for jobs."
        })


@tool
def match_job_to_skills(
    job_title: str,
    skills: str,
    experience_level: str = "",
    preferred_location: str = "",
    employment_type: str = "",
    top_k: int = 10,
    max_pages: int = 2,
) -> str:
    """Find jobs for a title and rank them against the candidate's skills.

    Provide candidate skills as a comma-separated string. Results include
    relative match scores, matched skills, and explanations. A match score
    is a ranking score, not the probability of getting hired.
    """

    if not isinstance(job_title, str) or not job_title.strip():
        return json.dumps({"error": "job_title must be a non-empty string"})

    if not isinstance(skills, str) or not skills.strip():
        return json.dumps({"error": "skills must be a non-empty string"})

    candidate_profile: dict[str, Any] = {
        "skills": [
            skill.strip()
            for skill in skills.split(",")
            if skill.strip()
        ]
    }

    if experience_level.strip():
        candidate_profile["experience_level"] = experience_level.strip()

    if preferred_location.strip():
        candidate_profile["preferred_locations"] = [
            preferred_location.strip()
    ]

    if employment_type.strip():
        candidate_profile["preferred_employment_types"] = [
            employment_type.strip()
    ]

    country = preferred_location.strip() or "India"

    try:
        with JobService() as service:
            result = service.search_and_match(
                candidate_profile=candidate_profile,
                query=job_title.strip(),
                country=country,
                max_pages=max_pages,
                top_k=top_k,
            )

        return _format_result(result)

    except (JobServiceError, ValueError) as error:
        return json.dumps({"error": str(error)}, ensure_ascii=False)
    except Exception:
        return json.dumps({
            "error": "An unexpected error occurred while matching jobs."
        })


TOOLS = [search_jobs, match_job_to_skills]
