import os
from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent

class Settings(BaseSettings):
    DAILY_EMAIL_CAP: int = 30
    DELAY_MIN_SECONDS: int = 60
    DELAY_MAX_SECONDS: int = 180
    DRY_RUN: bool = True
    DATABASE_URL: str = f"sqlite:///{BASE_DIR / 'intern_outreach.db'}"

    # LLM Settings
    LLM_PROVIDER: str = "gemini"  # "gemini" or "ollama"
    GEMINI_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-2.5-flash"
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL: str = "llama3.2"

    # LLM Call Constraints
    LLM_CALL_DELAY_SECONDS: float = 5.0
    LLM_MAX_RETRIES: int = 4
    LLM_BACKOFF_FACTOR: float = 2.0

    # Gmail OAuth Settings
    GMAIL_CLIENT_SECRET_FILE: str = "credentials.json"
    GMAIL_TOKEN_FILE: str = "token.json"

    model_config = SettingsConfigDict(
        env_file=str(BASE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
