from sqlalchemy import select
from sqlalchemy.orm import Session

from jobquest_ai.database.models.resume import Resume


class ResumeRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, **data) -> Resume:
        resume = Resume(**data)
        self.db.add(resume)
        self.db.commit()
        self.db.refresh(resume)
        return resume

    def get_by_id(self, resume_id: int) -> Resume | None:
        return self.db.get(Resume, resume_id)

    def list_by_user(
        self, user_id: int, skip: int = 0, limit: int = 50
    ) -> list[Resume]:
        statement = (
            select(Resume)
            .where(Resume.user_id == user_id)
            .order_by(Resume.created_at.desc())
            .offset(max(skip, 0))
            .limit(max(1, min(limit, 100)))
        )
        return list(self.db.scalars(statement).all())

    def update_extracted_data(
        self,
        resume: Resume,
        extracted_text: str,
        parsed_data: dict | None = None,
    ) -> Resume:
        resume.extracted_text = extracted_text
        resume.parsed_data = parsed_data
        self.db.commit()
        self.db.refresh(resume)
        return resume

    def delete(self, resume: Resume) -> None:
        self.db.delete(resume)
        self.db.commit()