
import logging
from typing import Any

import httpx


logger = logging.getLogger(__name__)

HIMALAYAS_API_URL = "https://himalayas.app/jobs/api/search"
DEFAULT_TIMEOUT = 30.0


class JobSearchError(Exception):
    """Raised when a job search request fails."""


def normalize_job(job: dict[str, Any]) -> dict[str, Any]:
    """
    Convert a raw Himalayas job into a consistent internal format.
    """

    external_id = job.get("guid")
    title = job.get("title")
    company = job.get("companyName")
    application_url = job.get("applicationLink")

    required_fields = {
        "guid": external_id,
        "title": title,
        "companyName": company,
        "applicationLink": application_url,
    }

    for field, value in required_fields.items():
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Missing or invalid field: {field}")

    parsed_url = httpx.URL(application_url.strip())

    if parsed_url.scheme not in ("http", "https") or not parsed_url.host:
        raise ValueError("Invalid application URL")

    locations = job.get("locationRestrictions") or []

    if not isinstance(locations, list):
        raise ValueError("locationRestrictions must be a list")

    return {
        "external_id": external_id.strip(),
        "title": title.strip(),
        "company_name": company.strip(),
        "application_url": application_url.strip(),
        "location_restrictions": locations,
        "employment_type": job.get("employmentType"),
        "description": job.get("description"),
        "excerpt": job.get("excerpt"),
        "min_salary": job.get("minSalary"),
        "max_salary": job.get("maxSalary"),
        "currency": job.get("currency"),
        "salary_period": job.get("salaryPeriod"),
        "seniority": job.get("seniority"),
        "published_at": job.get("pubDate"),
        "source": "himalayas",
    }


class HimalayasJobSearch:
    """
    Fetch and normalize jobs from the public Himalayas API.
    """

    def __init__(
        self,
        timeout: float = DEFAULT_TIMEOUT,
        client: httpx.Client | None = None,
    ):
        self._client = client or httpx.Client(
            timeout=timeout,
            headers={"Accept": "application/json"},
        )
        self._owns_client = client is None

    def close(self) -> None:
        """Close the HTTP client if this class created it."""

        if self._owns_client:
            self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()

    def search_jobs(
        self,
        query: str,
        country: str = "India",
        page: int = 1,
    ) -> dict[str, Any]:
        """
        Fetch and normalize jobs from one API page.
        """

        if not isinstance(query, str) or not query.strip():
            raise ValueError("query must be a non-empty string")

        if not isinstance(country, str) or not country.strip():
            raise ValueError("country must be a non-empty string")

        if isinstance(page, bool) or not isinstance(page, int) or page < 1:
            raise ValueError("page must be a positive integer")

        try:
            response = self._client.get(
                HIMALAYAS_API_URL,
                params={
                    "q": query.strip(),
                    "country": country.strip(),
                    "page": page,
                },
            )

            response.raise_for_status()
            data = response.json()

        except httpx.TimeoutException as error:
            raise JobSearchError(
                "Himalayas request timed out"
            ) from error

        except httpx.HTTPStatusError as error:
            status = error.response.status_code

            if status == 429:
                message = "Himalayas rate limit reached"
            else:
                message = f"Himalayas returned HTTP {status}"

            raise JobSearchError(message) from error

        except httpx.RequestError as error:
            raise JobSearchError(
                "Could not connect to Himalayas"
            ) from error

        except ValueError as error:
            raise JobSearchError(
                "Himalayas returned invalid JSON"
            ) from error

        if not isinstance(data, dict):
            raise JobSearchError(
                "Expected a JSON object in the response"
            )

        raw_jobs = data.get("jobs")

        if not isinstance(raw_jobs, list):
            raise JobSearchError(
                "Response does not contain a valid jobs list"
            )

        normalized_jobs = []
        rejected_count = 0

        for raw_job in raw_jobs:
            if not isinstance(raw_job, dict):
                rejected_count += 1
                continue

            try:
                normalized_jobs.append(normalize_job(raw_job))
            except (ValueError, TypeError):
                rejected_count += 1

        logger.info(
            "Himalayas search completed: query=%r page=%d "
            "valid=%d rejected=%d",
            query.strip(),
            page,
            len(normalized_jobs),
            rejected_count,
        )

        return {
            "query": query.strip(),
            "page": page,
            "total_count": data.get("totalCount"),
            "jobs": normalized_jobs,
            "returned_count": len(normalized_jobs),
            "rejected_count": rejected_count,
        }

    def search_multiple_pages(
        self,
        query: str,
        country: str = "India",
        max_pages: int = 2,
    ) -> dict[str, Any]:
        """
        Fetch multiple pages and remove duplicate jobs by external ID.
        """

        if (
            isinstance(max_pages, bool)
            or not isinstance(max_pages, int)
            or max_pages < 1
        ):
            raise ValueError("max_pages must be a positive integer")

        jobs_by_id: dict[str, dict[str, Any]] = {}
        total_count = None
        pages_fetched = 0
        rejected_count = 0

        for page in range(1, max_pages + 1):
            result = self.search_jobs(
                query=query,
                country=country,
                page=page,
            )

            pages_fetched += 1
            rejected_count += result["rejected_count"]

            if total_count is None:
                total_count = result["total_count"]

            for job in result["jobs"]:
                jobs_by_id.setdefault(job["external_id"], job)

            if not result["jobs"]:
                break

        return {
            "query": query.strip(),
            "total_count": total_count,
            "pages_fetched": pages_fetched,
            "jobs": list(jobs_by_id.values()),
            "returned_count": len(jobs_by_id),
            "rejected_count": rejected_count,
        }
