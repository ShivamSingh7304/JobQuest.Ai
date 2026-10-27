from sqlalchemy import select
from sqlalchemy.orm import Session

from jobquest_ai.database.models.job import Job

class JobRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, **data) -> Job:
        job = Job(**data)
        self.db.add(job)
        self.db.commit()
        self.db.refresh(job)
        return job

    def get_by_id(self, job_id: int) -> Job | None:
        return self.db.get(Job, job_id)

    def get_by_external_id(
        self, source: str, external_job_id: str
    ) -> Job | None:
        statement = select(Job).where(
            Job.source == source,
            Job.external_job_id == external_job_id,
        )
        return self.db.scalar(statement)

    def upsert_external_job(self, **data) -> Job:
        job = self.get_by_external_id(
            data["source"], data["external_job_id"]
        )

        if job is None:
            job = Job(**data)
            self.db.add(job)
        else:
            for key, value in data.items():
                if key not in {"id", "created_at"}:
                    setattr(job, key, value)

        self.db.commit()
        self.db.refresh(job)
        return job

    def search(
        self,
        keyword: str | None = None,
        location: str | None = None,
        work_mode: str | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> list[Job]:
        statement = select(Job)

        if keyword:
            pattern = f"%{keyword.strip()}%"
            statement = statement.where(
                Job.title.ilike(pattern)
                | Job.company.ilike(pattern)
                | Job.description.ilike(pattern)
            )

        if location:
            statement = statement.where(
                Job.location.ilike(f"%{location.strip()}%")
            )

        if work_mode:
            statement = statement.where(
                Job.work_mode.ilike(f"%{work_mode.strip()}%")
            )

        statement = (
            statement.order_by(Job.created_at.desc())
            .offset(max(skip, 0))
            .limit(max(1, min(limit, 100)))
        )
        return list(self.db.scalars(statement).all())

    def delete(self, job: Job) -> None:
        self.db.delete(job)
        self.db.commit()