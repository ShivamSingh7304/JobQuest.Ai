from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from jobquest_ai.database.connection import Base


class CalendarConnection(Base):
    __tablename__ = "calendar_connections"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    access_token: Mapped[str] = mapped_column(String(4096), nullable=False)
    refresh_token: Mapped[str | None] = mapped_column(String(4096), nullable=True)
    token_expiry: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
