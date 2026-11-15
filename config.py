import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent

class Settings(BaseSettings):
    DAILY_EMAIL_CAP: int = 30
    DELAY_MIN_SECONDS: int = 60
    DELAY_MAX_SECONDS: int = 180
    DRY_RUN: bool = True
    DATABASE_URL: str = f"sqlite:///{BASE_DIR / 'intern_outreach.db'}"

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
