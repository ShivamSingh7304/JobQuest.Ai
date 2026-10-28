from sqlalchemy.orm import Session

from jobquest_ai.database.repositories.resume_repository import ResumeRepository
from jobquest_ai.database.repositories.user_memory_repository import (
    UserMemoryRepository,
)
from jobquest_ai.memory.memory_extractor import MemoryExtractor
from jobquest_ai.memory.user_profile import UserProfile
from jobquest_ai.memory.user_md_manager import format_user_context


class MemoryManager:
    """Load, validate, and persist career memory for an individual user."""

    def __init__(
        self,
        db: Session,
        extractor: MemoryExtractor | None = None,
    ):
        self._memory_repository = UserMemoryRepository(db)
        self._resume_repository = ResumeRepository(db)
        self._extractor = extractor or MemoryExtractor()

    def get_profile(self, user_id: int) -> UserProfile:
        saved = self._memory_repository.get_by_user(user_id)
        profile = UserProfile()

        resumes = self._resume_repository.list_by_user(
            user_id,
            skip=0,
            limit=1,
        )
        if resumes and resumes[0].parsed_data:
            resume_data = dict(resumes[0].parsed_data)
            if not resume_data.get("preferred_roles"):
                resume_data["preferred_roles"] = resume_data.get(
                    "suggested_roles",
                    [],
                )
            profile = UserProfile.model_validate(resume_data)

        if saved is not None:
            profile = profile.merged_with(
                UserProfile.model_validate(saved.profile)
            )
        return profile

    def update_profile(
        self,
        user_id: int,
        profile: UserProfile | dict,
    ) -> UserProfile:
        validated = UserProfile.model_validate(profile)
        self._memory_repository.save_profile(
            user_id=user_id,
            profile=validated.model_dump(mode="json"),
        )
        return validated

    def update_from_conversation(
        self,
        user_id: int,
        conversation_text: str,
    ) -> UserProfile:
        extracted = self._extractor.extract(conversation_text)
        merged = self.get_profile(user_id).merged_with(extracted)
        return self.update_profile(user_id, merged)

    def get_context(self, user_id: int) -> str:
        return format_user_context(self.get_profile(user_id))