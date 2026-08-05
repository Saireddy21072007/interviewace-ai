"""
Configuration - one object, read from .env once, injected everywhere.

Nothing in the codebase calls os.getenv() for application settings. That rule
is what makes it possible to see the entire configuration surface of the
product by reading one file, and it is what keeps secrets out of the code.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- app ---
    app_name: str = "InterviewAce AI"
    version: str = "1.0.0"
    debug: bool = False

    # --- security ---
    secret_key: str = Field(default="dev-only-insecure-key-change-me")
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440
    admin_email: str = "admin@interviewace.ai"

    # --- database ---
    database_url: str = f"sqlite:///{(REPO_ROOT / 'interviewace.db').as_posix()}"

    # --- storage ---
    storage_dir: Path = REPO_ROOT / "storage"
    max_upload_mb: int = 10

    # --- ai ---
    llm_provider: str = "auto"
    llm_model: str = ""
    stt_provider: str = "auto"
    whisper_model: str = "base.en"

    # --- cors ---
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @field_validator("storage_dir", mode="after")
    @classmethod
    def _make_absolute(cls, value: Path) -> Path:
        return value if value.is_absolute() else (REPO_ROOT / value).resolve()

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    @property
    def max_upload_bytes(self) -> int:
        return self.max_upload_mb * 1024 * 1024

    @property
    def resume_dir(self) -> Path:
        return self.storage_dir / "resumes"

    @property
    def audio_dir(self) -> Path:
        return self.storage_dir / "audio"

    def ensure_dirs(self) -> None:
        for directory in (self.storage_dir, self.resume_dir, self.audio_dir):
            directory.mkdir(parents=True, exist_ok=True)

    def is_insecure_secret(self) -> bool:
        """True when the deployment is still using a placeholder signing key."""
        return self.secret_key in {"dev-only-insecure-key-change-me", "change-me-in-production"}


@lru_cache
def get_settings() -> Settings:
    """Cached so the .env file is parsed once per process."""
    settings = Settings()
    settings.ensure_dirs()
    return settings
