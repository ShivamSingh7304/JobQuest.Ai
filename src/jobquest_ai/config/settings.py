import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    groq_api_key: str | None = field(default=None, repr=False)
    groq_model: str = "openai/gpt-oss-120b"


def get_settings() -> Settings:
    """Load runtime settings from the environment and project .env file."""
    load_dotenv(Path(__file__).resolve().parents[3] / ".env")
    return Settings(
        groq_api_key=os.getenv("GROQ_API_KEY"),
        groq_model=os.getenv("GROQ_MODEL", "openai/gpt-oss-120b"),
    )