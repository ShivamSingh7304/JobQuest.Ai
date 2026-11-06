import os
import logging
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker


logger = logging.getLogger(__name__)

load_dotenv(Path(__file__).resolve().parents[3] / ".env")

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. Add it to the project .env file or environment."
    )

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
logger.info("database_engine_initialized dialect=%s", engine.dialect.name)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        logger.debug("database_session_opened")
        yield db
    finally:
        db.close()
        logger.debug("database_session_closed")


def create_tables():
    import jobquest_ai.database.models  # Register all models

    Base.metadata.create_all(bind=engine)
    logger.info("Database tables verified")

    # ``create_all`` does not alter an existing table. Keep local SQLite
    # databases created before workflow-output persistence compatible without
    # deleting feedback or requiring a destructive reset.
    inspector = inspect(engine)
    feedback_columns = {
        column["name"] for column in inspector.get_columns("human_feedback")
    } if "human_feedback" in inspector.get_table_names() else set()
    if feedback_columns and "workflow_output_record_id" not in feedback_columns:
        logger.info("database_migration_started table=human_feedback column=workflow_output_record_id")
        with engine.begin() as connection:
            connection.execute(
                text(
                    "ALTER TABLE human_feedback "
                    "ADD COLUMN workflow_output_record_id INTEGER"
                )
            )

    application_columns = (
        {
            column["name"]
            for column in inspector.get_columns("applications")
        }
        if "applications" in inspector.get_table_names()
        else set()
    )
    if application_columns and "workflow_output_id" not in application_columns:
        logger.info("database_migration_started table=applications column=workflow_output_id")
        with engine.begin() as connection:
            connection.execute(
                text(
                    "ALTER TABLE applications "
                    "ADD COLUMN workflow_output_id INTEGER "
                    "REFERENCES workflow_outputs(id) ON DELETE SET NULL"
                )
            )
