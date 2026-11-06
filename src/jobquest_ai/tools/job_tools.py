
"""Job search and job-matching tools."""

import json
import contextvars
from typing import Any

from langchain_core.tools import tool
from sqlalchemy import select
from sqlalchemy.orm import Session

from jobquest_ai.database.models.application import Application
from jobquest_ai.database.models.job import Job
from jobquest_ai.database.models.resume import Resume
from jobquest_ai.jobs.job_service import JobService, JobServiceError
from jobquest_ai.jobs.job_matcher import JobMatcher

_job_context: contextvars.ContextVar[tuple[Session, int] | None] = contextvars.ContextVar(
    "jobquest_job_context", default=None
)


def set_job_context(db: Session, user_id: int):
    return _job_context.set((db, user_id))


def reset_job_context(token: contextvars.Token):
    _job_context.reset(token)


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


@tool
def rank_saved_jobs() -> str:
    """Rank the authenticated user's saved jobs against their latest resume.

    Use this when the user asks which saved job, saved opportunity, or saved
    application fits them best. Never ask the user to paste saved jobs first.
    """
    context = _job_context.get()
    if context is None:
        return json.dumps({"success": False, "error": "User job context is unavailable."})

    db, user_id = context
    rows = db.execute(
        select(Application, Job)
        .join(Job, Application.job_id == Job.id)
        .where(Application.user_id == user_id)
        .order_by(Application.updated_at.desc())
    ).all()
    if not rows:
        return json.dumps({"success": True, "saved_job_count": 0, "jobs": []})

    resume = db.scalar(
        select(Resume)
        .where(Resume.user_id == user_id)
        .order_by(Resume.created_at.desc())
    )
    profile = dict(resume.parsed_data or {}) if resume and resume.parsed_data else {}
    jobs = []
    for application, job in rows:
        jobs.append({
            "application_id": application.id,
            "application_status": application.status,
            "job_id": job.id,
            "external_job_id": job.external_job_id,
            "title": job.title,
            "company": job.company,
            "description": job.description or "",
            "location": job.location,
            "work_mode": job.work_mode,
            "employment_type": job.employment_type,
            "apply_url": job.apply_url,
        })

    ranked = JobMatcher().match_jobs(
        candidate_profile=profile,
        jobs=jobs,
        top_k=len(jobs),
    ) if profile else jobs
    return _format_result({
        "success": True,
        "saved_job_count": len(ranked),
        "resume_available": bool(profile),
        "jobs": ranked,
    })


TOOLS = [search_jobs, match_job_to_skills, rank_saved_jobs]
