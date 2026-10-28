from sqlalchemy.orm import Session

from jobquest_ai.database.models.user_memory import UserMemory


class UserMemoryRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_by_user(self, user_id: int) -> UserMemory | None:
        return self.db.get(UserMemory, user_id)

    def save_profile(
        self,
        user_id: int,
        profile: dict,
    ) -> UserMemory:
        memory = self.get_by_user(user_id)
        if memory is None:
            memory = UserMemory(user_id=user_id, profile=profile)
            self.db.add(memory)
        else:
            memory.profile = profile

        self.db.commit()
        self.db.refresh(memory)
        return memory
