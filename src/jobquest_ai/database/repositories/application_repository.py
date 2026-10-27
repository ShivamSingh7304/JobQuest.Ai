from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from jobquest_ai.database.models.application import Application


class ApplicationRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(self, **data) -> Application:
        application = Application(**data)
        self.db.add(application)
        self.db.commit()
        self.db.refresh(application)
        return application

    def get_by_id(self, application_id: int) -> Application | None:
        return self.db.get(Application, application_id)

    def list_by_user(
        self,
        user_id: int,
        status: str | None = None,
        skip: int = 0,
        limit: int = 50,
    ) -> list[Application]:
        statement = select(Application).where(
            Application.user_id == user_id
        )

        if status:
            statement = statement.where(
                Application.status == status
            )

        statement = (
            statement.order_by(Application.updated_at.desc())
            .offset(max(skip, 0))
            .limit(max(1, min(limit, 100)))
        )
        return list(self.db.scalars(statement).all())

    def update_status(
        self,
        application: Application,
        status: str,
        notes: str | None = None,
    ) -> Application:
        allowed = {
            "saved", "pending_approval", "approved", "submitted",
            "interviewing", "rejected", "offer", "withdrawn",
        }
        if status not in allowed:
            raise ValueError(f"Invalid application status: {status}")

        application.status = status
        if notes is not None:
            application.notes = notes

        if status == "submitted" and application.applied_at is None:
            application.applied_at = datetime.now(timezone.utc)

        self.db.commit()
        self.db.refresh(application)
        return application

    def delete(self, application: Application) -> None:
        self.db.delete(application)
        self.db.commit()