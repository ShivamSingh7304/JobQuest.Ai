from sqlalchemy import select
from sqlalchemy.orm import Session

from jobquest_ai.database.models.user import User


class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def create(
        self,
        full_name: str,
        email: str,
        password_hash: str,
    ) -> User:
        user = User(
            full_name=full_name,
            email=email.strip().lower(),
            password_hash=password_hash,
        )
        self.db.add(user)
        self.db.commit()
        self.db.refresh(user)
        return user

    def get_by_id(self, user_id: int) -> User | None:
        return self.db.get(User, user_id)

    def get_by_email(self, email: str) -> User | None:
        statement = select(User).where(
            User.email == email.strip().lower()
        )
        return self.db.scalar(statement)

    def list_users(self, skip: int = 0, limit: int = 100) -> list[User]:
        statement = (
            select(User)
            .order_by(User.id)
            .offset(skip)
            .limit(min(limit, 100))
        )
        return list(self.db.scalars(statement).all())

    def update(self, user: User, **fields) -> User:
        allowed = {"full_name", "email", "is_active"}
        for key, value in fields.items():
            if key in allowed:
                setattr(
                    user,
                    key,
                    value.strip().lower()
                    if key == "email" and isinstance(value, str)
                    else value,
                )
        self.db.commit()
        self.db.refresh(user)
        return user

    def update_password(
        self, user: User, password_hash: str
    ) -> User:
        user.password_hash = password_hash
        self.db.commit()
        self.db.refresh(user)
        return user

    def delete(self, user: User) -> None:
        self.db.delete(user)
        self.db.commit()