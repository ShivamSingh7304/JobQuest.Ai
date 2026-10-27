from sqlalchemy.orm import Session

from jobquest_ai.auth.jwt import create_access_token
from jobquest_ai.auth.password import hash_password, verify_password
from jobquest_ai.database.models.user import User
from jobquest_ai.database.repositories.user_repository import UserRepository


class AuthService:
    def __init__(self, db: Session):
        self.users = UserRepository(db)

    def register(
        self,
        full_name: str,
        email: str,
        password: str,
    ) -> User:
        full_name = full_name.strip()
        email = email.strip().lower()

        if not full_name:
            raise ValueError("Full name is required.")

        if len(full_name) > 150:
            raise ValueError("Full name must be at most 150 characters.")

        if self.users.get_by_email(email):
            raise ValueError("An account with this email already exists.")

        password_hash = hash_password(password)

        return self.users.create(
            full_name=full_name,
            email=email,
            password_hash=password_hash,
        )

    def login(self, email: str, password: str) -> dict:
        user = self.users.get_by_email(email.strip().lower())

        if user is None or not verify_password(
            password, user.password_hash
        ):
            raise ValueError("Invalid email or password.")

        if not user.is_active:
            raise ValueError("This account is inactive.")

        return {
            "access_token": create_access_token(user.id),
            "token_type": "bearer",
        }