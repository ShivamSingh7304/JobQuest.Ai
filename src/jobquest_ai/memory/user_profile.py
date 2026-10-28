from typing import Any

from pydantic import BaseModel, ConfigDict, Field

_PROFILE_LIST_LIMITS = {
    "career_goals": 50,
    "preferred_roles": 50,
    "skills": 200,
    "experience": 50,
    "education": 50,
    "projects": 50,
    "certifications": 50,
    "preferred_locations": 50,
    "preferred_employment_types": 50,
    "preferred_work_modes": 20,
}


class UserProfile(BaseModel):
    """Validated, career-focused context retained for one user."""

    model_config = ConfigDict(extra="ignore")

    candidate_summary: str = Field(default="", max_length=2000)
    career_goals: list[str] = Field(default_factory=list, max_length=50)
    preferred_roles: list[str] = Field(default_factory=list, max_length=50)
    skills: list[str] = Field(default_factory=list, max_length=200)
    experience: list[dict[str, Any]] = Field(default_factory=list, max_length=50)
    education: list[dict[str, Any]] = Field(default_factory=list, max_length=50)
    projects: list[dict[str, Any]] = Field(default_factory=list, max_length=50)
    certifications: list[dict[str, Any]] = Field(default_factory=list, max_length=50)
    preferred_locations: list[str] = Field(default_factory=list, max_length=50)
    preferred_employment_types: list[str] = Field(
        default_factory=list,
        max_length=50,
    )
    preferred_work_modes: list[str] = Field(default_factory=list, max_length=20)

    def merged_with(self, newer: "UserProfile") -> "UserProfile":
        """Return a profile that retains existing facts and adds new ones."""
        values = self.model_dump()
        newer_values = newer.model_dump()

        if newer.candidate_summary:
            values["candidate_summary"] = newer.candidate_summary

        for field_name, new_value in newer_values.items():
            if field_name == "candidate_summary":
                continue
            if not isinstance(new_value, list):
                continue

            merged = []
            for item in (*new_value, *values[field_name]):
                if item not in merged:
                    merged.append(item)
            values[field_name] = merged[: _PROFILE_LIST_LIMITS[field_name]]

        return UserProfile.model_validate(values)