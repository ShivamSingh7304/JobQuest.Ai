
"""Workflow for discovering and optionally matching jobs."""

from typing import Any, Callable

from jobquest_ai.jobs.job_search import JobSearchError
from jobquest_ai.jobs.job_service import JobService, JobServiceError


class JobDiscoveryError(Exception):
    """Raised when the job discovery workflow cannot complete."""


class JobDiscoveryWorkflow:
    """Coordinate job search and optional candidate-specific matching."""

    def __init__(
        self,
        service_factory: Callable[[], JobService] = JobService,
    ) -> None:
        self._service_factory = service_factory

    def discover_jobs(
        self,
        role: str,
        location: str = "India",
        work_mode: str = "any",
        candidate_profile: dict[str, Any] | None = None,
        max_pages: int = 2,
        top_k: int = 10,
    ) -> dict[str, Any]:
        """Search for jobs, optionally ranking them for a candidate.

        work_mode is recorded as a preference but is not currently
        applied as a provider-side filter.
        """
        self._validate_inputs(
            role=role,
            location=location,
            work_mode=work_mode,
            candidate_profile=candidate_profile,
            max_pages=max_pages,
            top_k=top_k,
        )

        role = role.strip()
        location = location.strip()
        work_mode = work_mode.strip().lower()
        mode = "match" if candidate_profile is not None else "search"

        try:
            with self._service_factory() as service:
                if candidate_profile is not None:
                    result = service.search_and_match(
                        candidate_profile=candidate_profile,
                        query=role,
                        country=location,
                        max_pages=max_pages,
                        top_k=top_k,
                    )

                    jobs = result["jobs"]
                    response = {
                        **result,
                        "mode": mode,
                        "work_mode_requested": work_mode,
                        "work_mode_filter_applied": False,
                        "returned_job_count": len(jobs),
                    }
                else:
                    search_result = (
                        service.job_search.search_multiple_pages(
                            query=role,
                            country=location,
                            max_pages=max_pages,
                        )
                    )

                    jobs = search_result["jobs"][:top_k]

                    response = {
                        "query": search_result["query"],
                        "country": location,
                        "mode": mode,
                        "work_mode_requested": work_mode,
                        "work_mode_filter_applied": False,
                        "total_count": search_result["total_count"],
                        "pages_fetched": search_result["pages_fetched"],
                        "fetched_job_count": (
                            search_result["returned_count"]
                        ),
                        "rejected_job_count": (
                            search_result["rejected_count"]
                        ),
                        "returned_job_count": len(jobs),
                        "jobs": jobs,
                    }

        except (JobServiceError, JobSearchError, ValueError) as error:
            raise JobDiscoveryError(
                f"Job discovery failed: {error}"
            ) from error

        response["status"] = (
            "success" if response["jobs"] else "no_results"
        )
        return response

    @staticmethod
    def _validate_inputs(
        role: str,
        location: str,
        work_mode: str,
        candidate_profile: dict[str, Any] | None,
        max_pages: int,
        top_k: int,
    ) -> None:
        if not isinstance(role, str) or not role.strip():
            raise ValueError("role must be a non-empty string")

        if not isinstance(location, str) or not location.strip():
            raise ValueError("location must be a non-empty string")

        if not isinstance(work_mode, str) or not work_mode.strip():
            raise ValueError("work_mode must be a non-empty string")

        if candidate_profile is not None:
            if not isinstance(candidate_profile, dict):
                raise ValueError(
                    "candidate_profile must be a dictionary"
                )

            skills = candidate_profile.get("skills")
            if not isinstance(skills, list) or not any(
                isinstance(skill, str) and skill.strip()
                for skill in skills
            ):
                raise ValueError(
                    "candidate_profile must contain at least one skill"
                )

        if (
            isinstance(max_pages, bool)
            or not isinstance(max_pages, int)
            or max_pages < 1
        ):
            raise ValueError("max_pages must be a positive integer")

        if (
            isinstance(top_k, bool)
            or not isinstance(top_k, int)
            or top_k < 1
        ):
            raise ValueError("top_k must be a positive integer")
