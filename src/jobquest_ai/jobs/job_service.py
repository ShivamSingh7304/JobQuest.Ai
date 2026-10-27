
from typing import Any

from jobquest_ai.jobs.job_matcher import (
    JobMatcher,
    JobMatchingError,
)
from jobquest_ai.jobs.job_search import (
    HimalayasJobSearch,
    JobSearchError,
)


class JobServiceError(Exception):
    """Raised when the job search and matching workflow fails."""


class JobService:
    """
    Coordinate job retrieval and candidate-job matching.

    JobSearch retrieves normalized jobs.
    JobMatcher scores and ranks those jobs.
    """

    def __init__(
        self,
        job_search: HimalayasJobSearch | None = None,
        matcher: JobMatcher | None = None,
    ):
        self._owns_job_search = job_search is None

        self.job_search = job_search or HimalayasJobSearch()
        self.matcher = matcher or JobMatcher()

    def close(self) -> None:
        """Close the search client when this service owns it."""
        if self._owns_job_search:
            self.job_search.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def search_and_match(
        self,
        candidate_profile: dict[str, Any],
        query: str,
        country: str = "India",
        max_pages: int = 2,
        top_k: int = 10,
    ) -> dict[str, Any]:
        """
        Fetch jobs, rank them against a candidate profile,
        and return ranked results with search metadata.
        """

        if not isinstance(candidate_profile, dict):
            raise ValueError(
                "candidate_profile must be a dictionary"
            )

        if not isinstance(query, str) or not query.strip():
            raise ValueError(
                "query must be a non-empty string"
            )

        if not isinstance(country, str) or not country.strip():
            raise ValueError(
                "country must be a non-empty string"
            )

        if (
            isinstance(max_pages, bool)
            or not isinstance(max_pages, int)
            or max_pages < 1
        ):
            raise ValueError(
                "max_pages must be a positive integer"
            )

        if (
            isinstance(top_k, bool)
            or not isinstance(top_k, int)
            or top_k < 1
        ):
            raise ValueError(
                "top_k must be a positive integer"
            )

        try:
            search_result = self.job_search.search_multiple_pages(
                query=query.strip(),
                country=country.strip(),
                max_pages=max_pages,
            )

            jobs = search_result["jobs"]

            ranked_jobs = self.matcher.match_jobs(
                candidate_profile=candidate_profile,
                jobs=jobs,
                top_k=top_k,
            )

        except (JobSearchError, JobMatchingError) as error:
            raise JobServiceError(
                f"Job search and matching failed: {error}"
            ) from error

        return {
            "query": search_result["query"],
            "country": country.strip(),
            "total_count": search_result["total_count"],
            "pages_fetched": search_result["pages_fetched"],
            "fetched_job_count": search_result["returned_count"],
            "rejected_job_count": search_result["rejected_count"],
            "matched_job_count": len(ranked_jobs),
            "match_score_type": (
                "Relative ranking score, not hiring probability"
            ),
            "jobs": ranked_jobs,
        }
