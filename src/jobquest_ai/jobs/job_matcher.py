import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

# These are ranking weights, not probabilities of being hired.
MATCH_WEIGHTS = {
    "skills": 0.30,
    "role": 0.15,
    "experience": 0.10,
    "preferences": 0.10,
    "semantic": 0.35,
}

DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


class JobMatchingError(Exception):
    """Raised when job matching cannot be completed."""


def _as_list(value: Any) -> list[str]:
    """Convert a list of non-empty strings into a clean list."""
    if not isinstance(value, list):
        return []
    return [item.strip() for item in value if isinstance(item, str) and item.strip()]


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.lower()).strip()


def _contains_phrase(text: str, phrase: str) -> bool:
    text = _normalize_text(text)
    phrase = _normalize_text(phrase)
    if not text or not phrase:
        return False
    return re.search(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", text) is not None


def _unique(values: list[str]) -> list[str]:
    result = []
    seen = set()
    for value in values:
        normalized = _normalize_text(value)
        if normalized and normalized not in seen:
            seen.add(normalized)
            result.append(value.strip())
    return result


def normalize_candidate_profile(profile: dict[str, Any]) -> dict[str, Any]:
    """Normalize resume-analyzer output or a manually entered candidate profile."""
    if not isinstance(profile, dict):
        raise ValueError("Candidate profile must be a dictionary")

    skills = []
    for key in (
        "skills",
        "programming_languages",
        "frameworks_and_libraries",
        "tools_and_platforms",
    ):
        skills.extend(_as_list(profile.get(key)))
    skills = _unique(skills)

    requested_roles = _as_list(profile.get("preferred_roles"))
    suggested_roles = _as_list(profile.get("suggested_roles"))
    preferred_roles = requested_roles or suggested_roles

    experience = profile.get("experience", [])
    if not isinstance(experience, list):
        experience = []
    experience = [item for item in experience if isinstance(item, dict)]

    responsibilities = []
    for item in experience:
        responsibilities.extend(_as_list(item.get("responsibilities")))

    project_text = []
    projects = profile.get("projects", [])
    if isinstance(projects, list):
        for project in projects:
            if isinstance(project, str):
                project_text.append(project)
            elif isinstance(project, dict):
                for key in ("name", "title", "description", "technologies"):
                    value = project.get(key)
                    if isinstance(value, str):
                        project_text.append(value)
                    elif isinstance(value, list):
                        project_text.extend(_as_list(value))

    summary = profile.get("candidate_summary", "")
    if not isinstance(summary, str):
        summary = ""

    experience_level = profile.get("experience_level", "")
    if not isinstance(experience_level, str):
        experience_level = ""

    years = profile.get("years_experience", profile.get("experience_years"))
    try:
        years = float(years) if years is not None and str(years).strip() else None
        if years is not None and (years < 0 or years > 80):
            years = None
    except (TypeError, ValueError):
        years = None

    return {
        "candidate_summary": summary,
        "skills": skills,
        "preferred_roles": preferred_roles,
        "experience_level": experience_level.strip(),
        "years_experience": years,
        "preferred_locations": _as_list(profile.get("preferred_locations")),
        "preferred_employment_types": _as_list(profile.get("preferred_employment_types")),
        "experience": experience,
        "responsibilities": responsibilities,
        "project_text": project_text,
        "education": profile.get("education", []),
    }


def _candidate_text(candidate: dict[str, Any]) -> str:
    parts = [
        candidate["candidate_summary"],
        "Skills: " + ", ".join(candidate["skills"]),
        "Target roles: " + ", ".join(candidate["preferred_roles"]),
        "Experience: " + " ".join(candidate["responsibilities"]),
        "Projects: " + " ".join(candidate["project_text"]),
    ]
    return "\n".join(part for part in parts if part.strip())


def _job_text(job: dict[str, Any]) -> str:
    fields = [
        job.get("title"),
        job.get("description"),
        job.get("excerpt"),
        job.get("company_name"),
        job.get("employment_type"),
        job.get("seniority"),
    ]
    return "\n".join(value for value in fields if isinstance(value, str) and value.strip())


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"[\n.!?;]+", text) if part.strip()]


def _skill_context(skill: str, job_text: str) -> str:
    """Classify a candidate skill's mentions using nearby wording.

    This is deliberately heuristic: it does not extract every possible skill
    from a job posting or guarantee that a requirement was classified correctly.
    """
    required_markers = (
        "required", "must have", "must-have", "mandatory", "essential",
        "minimum qualifications", "basic qualifications", "you will need",
        "requirements", "need to have",
    )
    preferred_markers = (
        "preferred", "nice to have", "nice-to-have", "bonus",
        "desirable", "ideally", "a plus", "preferred qualifications",
    )

    matching_sentences = [
        sentence for sentence in _sentences(job_text)
        if _contains_phrase(sentence, skill)
    ]
    if not matching_sentences:
        return "unverified"

    labels = []
    for sentence in matching_sentences:
        lowered = _normalize_text(sentence)
        if any(marker in lowered for marker in required_markers):
            labels.append("required")
        elif any(marker in lowered for marker in preferred_markers):
            labels.append("preferred")
        else:
            labels.append("other")

    # When the same skill appears in multiple contexts, retain the strongest
    # explicit signal, while acknowledging that the classification is inferred.
    if "required" in labels:
        return "required"
    if "preferred" in labels:
        return "preferred"
    return "other"


def _skill_score(candidate_skills: list[str], job_text: str) -> dict[str, Any]:
    """Score evidence that candidate-listed skills are relevant to the posting."""
    if not candidate_skills or not job_text.strip():
        return {
            "score": 50.0,
            "matched_skills": [],
            "required_skills_matched": [],
            "preferred_skills_matched": [],
            "other_skills_matched": [],
            "unverified_skills": candidate_skills.copy(),
            "available": False,
            "classification_note": "Insufficient text to assess skill mentions",
        }

    categories = {kind: [] for kind in ("required", "preferred", "other", "unverified")}
    # A required-context mention contributes more than a preferred or general mention.
    values = {"required": 1.0, "preferred": 0.7, "other": 0.4, "unverified": 0.0}
    for skill in candidate_skills:
        categories[_skill_context(skill, job_text)].append(skill)

    score = 100.0 * sum(
        values[kind] * len(skills) for kind, skills in categories.items()
    ) / len(candidate_skills)

    matched = categories["required"] + categories["preferred"] + categories["other"]
    return {
        "score": round(score, 2),
        "matched_skills": matched,
        "required_skills_matched": categories["required"],
        "preferred_skills_matched": categories["preferred"],
        "other_skills_matched": categories["other"],
        "unverified_skills": categories["unverified"],
        "available": True,
        "classification_note": (
            "Required/preferred labels are inferred from nearby job-description wording."
        ),
    }


def _role_score(preferred_roles: list[str], job_title: str) -> dict[str, Any]:
    if not preferred_roles or not job_title.strip():
        return {"score": 50.0, "matched_role": None, "available": False}

    title_tokens = set(re.findall(r"\b[a-z0-9+#.]+\b", _normalize_text(job_title)))
    best_score = 0.0
    best_role = None
    for role in preferred_roles:
        role_tokens = set(re.findall(r"\b[a-z0-9+#.]+\b", _normalize_text(role)))
        if not role_tokens:
            continue
        overlap = len(title_tokens & role_tokens)
        score = 100.0 * overlap / len(role_tokens)
        if score > best_score:
            best_score, best_role = score, role

    return {
        "score": round(best_score, 2),
        "matched_role": best_role if best_score > 0 else None,
        "available": True,
        "method": "title token overlap heuristic",
    }


def _job_experience_range(job_text: str) -> tuple[float | None, float | None]:
    """Extract simple years-of-experience ranges from common posting wording."""
    text = _normalize_text(job_text)
    patterns = [
        # e.g. 3-5 years of experience, 3 to 5 years' experience
        r"\b(\d+(?:\.\d+)?)\s*(?:-|to)\s*(\d+(?:\.\d+)?)\s*\+?\s*years?\s+(?:of\s+)?experience\b",
        # e.g. 3+ years of experience, at least 3 years' experience
        r"\b(?:at least\s+)?(\d+(?:\.\d+)?)\s*\+\s*years?\s+(?:of\s+)?experience\b",
        r"\b(?:at least|minimum of|min\.?)\s+(\d+(?:\.\d+)?)\s+years?\s+(?:of\s+)?experience\b",
    ]
    for index, pattern in enumerate(patterns):
        match = re.search(pattern, text)
        if match:
            minimum = float(match.group(1))
            maximum = float(match.group(2)) if index == 0 else None
            return minimum, maximum
    return None, None



def _level_from_text(text: str) -> str | None:
    text = _normalize_text(text)

    if any(term in text for term in (
        "fresher",
        "fresh graduate",
        "new graduate",
        "intern",
        "entry-level",
        "entry level",
        "junior",
        "graduate",
        "associate",
    )):
        return "entry"

    if any(term in text for term in (
        "senior",
        "staff engineer",
        "principal",
        "lead engineer",
        "director",
    )):
        return "senior"

    if any(term in text for term in (
        "mid-level",
        "mid level",
        "intermediate",
    )):
        return "mid"

    return None



def _experience_score(
    experience_level: str,
    job: dict[str, Any],
    years_experience: float | None = None,
) -> dict[str, Any]:
    """Compare explicit years where possible, otherwise use a labeled level heuristic."""
    job_text = _job_text(job)
    minimum, maximum = _job_experience_range(job_text)

    if years_experience is not None and minimum is not None:
        if years_experience < minimum:
            # Partial credit rather than a binary rejection; the score is only a ranking signal.
            score = max(0.0, 100.0 * years_experience / minimum) if minimum else 100.0
            status = "below_stated_minimum"
        elif maximum is not None and years_experience > maximum:
            score = 80.0
            status = "above_stated_range"
        else:
            score = 100.0
            status = "within_stated_range"
        return {
            "score": round(score, 2),
            "available": True,
            "status": status,
            "candidate_years": years_experience,
            "job_minimum_years": minimum,
            "job_maximum_years": maximum,
            "method": "explicit years comparison; job text extraction is heuristic",
        }

    candidate_level = _level_from_text(experience_level)
    job_level = _level_from_text(
        str(job.get("seniority") or "") + " " + str(job.get("title") or "")
    )
    if candidate_level and job_level:
        if candidate_level == job_level:
            score = 100.0
        elif {candidate_level, job_level} == {"entry", "senior"}:
            score = 0.0
        else:
            score = 50.0
        return {
            "score": score,
            "available": True,
            "status": "level_heuristic",
            "candidate_level": candidate_level,
            "job_level": job_level,
            "method": "seniority keyword heuristic; not a years-of-experience comparison",
        }

    reason = "Candidate years or job experience requirement not available"
    if not candidate_level:
        reason = "Candidate experience level/years not provided or not recognized"
    elif not job_level and minimum is None:
        reason = "Job experience requirement/seniority not stated clearly"
    return {
        "score": 50.0,
        "available": False,
        "status": "unknown",
        "candidate_years": years_experience,
        "job_minimum_years": minimum,
        "job_maximum_years": maximum,
        "reason": reason,
    }


def _preference_score(candidate: dict[str, Any], job: dict[str, Any]) -> dict[str, Any]:
    """Evaluate preferences with matched, not_matched, or unknown evidence."""
    checks = []
    reasons = []
    statuses = {}

    locations = candidate["preferred_locations"]
    if locations:
        raw_locations = job.get("location_restrictions")
        if isinstance(raw_locations, list):
            location_text = " ".join(str(value) for value in raw_locations)
        elif isinstance(raw_locations, str):
            location_text = raw_locations
        else:
            location_text = ""
        location_text += " " + str(job.get("title") or "")
        location_text += " " + str(job.get("description") or "")
        location_text += " " + str(job.get("excerpt") or "")
        location_text = _normalize_text(location_text)

        if not location_text.strip():
            status = "unknown"
        elif any(_contains_phrase(location_text, loc) for loc in locations):
            status = "matched"
        else:
            # If the posting has some location data but not the requested location,
            # it is only a conflict when location restrictions are explicitly supplied.
            if raw_locations:
                status = "not_matched"
            else:
                status = "unknown"
        statuses["location"] = status
        reasons.append(f"Location preference: {status.replace('_', ' ')}")
        if status != "unknown":
            checks.append(100.0 if status == "matched" else 0.0)

    employment_types = candidate["preferred_employment_types"]
    if employment_types:
        job_type = _normalize_text(str(job.get("employment_type") or ""))
        if not job_type:
            status = "unknown"
        elif any(
            _normalize_text(item) == job_type
            or _normalize_text(item) in job_type
            or job_type in _normalize_text(item)
            for item in employment_types
        ):
            status = "matched"
        else:
            status = "not_matched"
        statuses["employment_type"] = status
        reasons.append(f"Employment type preference: {status.replace('_', ' ')}")
        if status != "unknown":
            checks.append(100.0 if status == "matched" else 0.0)

    return {
        "score": round(sum(checks) / len(checks), 2) if checks else 50.0,
        "available": bool(checks),
        "status_by_preference": statuses,
        "reasons": reasons,
        "note": "Unknown preferences are excluded from the preference score.",
    }


class JobMatcher:
    """Hybrid job matcher using transparent heuristics and semantic similarity."""

    def __init__(self, model_name: str = DEFAULT_EMBEDDING_MODEL):
        self.model_name = model_name
        self._model = None

    def _get_model(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as error:
                raise JobMatchingError(
                    "Install sentence-transformers with "
                    "'python -m pip install sentence-transformers'"
                ) from error
            try:
                self._model = SentenceTransformer(self.model_name)
            except Exception as error:
                raise JobMatchingError(
                    f"Could not load embedding model: {self.model_name}"
                ) from error
        return self._model

    def _semantic_scores(
        self,
        candidate: dict[str, Any],
        jobs: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        candidate_text = _candidate_text(candidate)
        job_texts = [_job_text(job) for job in jobs]
        scores = [{"score": 50.0, "available": False, "cosine_similarity": None} for _ in jobs]

        if not candidate_text.strip():
            return scores
        valid_indices = [i for i, text in enumerate(job_texts) if text.strip()]
        if not valid_indices:
            return scores

        model = self._get_model()
        try:
            embeddings = model.encode(
                [candidate_text, *[job_texts[i] for i in valid_indices]],
                normalize_embeddings=True,
                convert_to_numpy=True,
            )
        except Exception as error:
            raise JobMatchingError("Failed to generate semantic embeddings") from error

        candidate_embedding = embeddings[0]
        for position, job_index in enumerate(valid_indices, start=1):
            similarity = float(candidate_embedding @ embeddings[position])
            # Keep the cosine similarity visible. The 0-100 value is only a
            # convenient rescaled ranking component, not a hiring probability.
            ranking_score = max(0.0, min(100.0, similarity * 100.0))
            scores[job_index] = {
                "score": round(ranking_score, 2),
                "cosine_similarity": round(similarity, 4),
                "available": True,
                "method": "cosine similarity; not a hiring probability",
            }
        return scores

    def match_jobs(
        self,
        candidate_profile: dict[str, Any],
        jobs: list[dict[str, Any]],
        top_k: int = 10,
    ) -> list[dict[str, Any]]:
        """Rank normalized jobs against a resume or manual candidate profile."""
        if not isinstance(top_k, int) or isinstance(top_k, bool) or top_k < 1:
            raise ValueError("top_k must be a positive integer")
        if not isinstance(jobs, list):
            raise ValueError("jobs must be a list")
        candidate = normalize_candidate_profile(candidate_profile)
        if not jobs:
            return []
        if any(not isinstance(job, dict) for job in jobs):
            raise ValueError("Every job must be a dictionary")

        semantic_results = self._semantic_scores(candidate, jobs)
        ranked_jobs = []

        for index, job in enumerate(jobs):
            text = _job_text(job)
            skill_result = _skill_score(candidate["skills"], text)
            role_result = _role_score(candidate["preferred_roles"], str(job.get("title") or ""))
            experience_result = _experience_score(
                candidate["experience_level"], job, candidate["years_experience"]
            )
            preference_result = _preference_score(candidate, job)
            semantic_result = semantic_results[index]

            components = {
                "skills": skill_result,
                "role": role_result,
                "experience": experience_result,
                "preferences": preference_result,
                "semantic": semantic_result,
            }
            active_weight = sum(
                MATCH_WEIGHTS[name]
                for name, result in components.items()
                if result["available"]
            )
            if active_weight:
                match_score = sum(
                    MATCH_WEIGHTS[name] * result["score"]
                    for name, result in components.items()
                    if result["available"]
                ) / active_weight
            else:
                match_score = 0.0

            reasons = []
            if skill_result["required_skills_matched"]:
                reasons.append(
                    "Candidate skills mentioned in required-context wording: "
                    + ", ".join(skill_result["required_skills_matched"])
                )
            if skill_result["preferred_skills_matched"]:
                reasons.append(
                    "Candidate skills mentioned in preferred-context wording: "
                    + ", ".join(skill_result["preferred_skills_matched"])
                )
            if skill_result["other_skills_matched"]:
                reasons.append(
                    "Other candidate skills mentioned: "
                    + ", ".join(skill_result["other_skills_matched"])
                )
            if role_result["matched_role"]:
                reasons.append("Related to target role: " + role_result["matched_role"])
            reasons.extend(preference_result["reasons"])
            if not reasons:
                reasons.append("Limited explicit matching evidence")

            ranked_jobs.append({
                **job,
                "match_score": round(match_score, 2),
                "match_score_type": "relative ranking score, not hiring probability",
                "match_components": {
                    name: result["score"] for name, result in components.items()
                },
                "semantic_similarity": semantic_result.get("cosine_similarity"),
                "matched_skills": skill_result["matched_skills"],
                "required_skills_matched": skill_result["required_skills_matched"],
                "preferred_skills_matched": skill_result["preferred_skills_matched"],
                "other_skills_matched": skill_result["other_skills_matched"],
                "unverified_skills": skill_result["unverified_skills"],
                "skill_classification_note": skill_result["classification_note"],
                "matched_role": role_result["matched_role"],
                "match_reasons": reasons,
                "experience_match": experience_result,
                "preference_match": preference_result,
            })

        ranked_jobs.sort(key=lambda item: item["match_score"], reverse=True)
        for rank, job in enumerate(ranked_jobs, start=1):
            job["match_rank"] = rank
        return ranked_jobs[:top_k]
