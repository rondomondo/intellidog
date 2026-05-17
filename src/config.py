from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment variables or .env file."""

    model_config = SettingsConfigDict(env_prefix="INTELLIDOG_", env_file=".env", env_file_encoding="utf-8")

    env: str = "development"
    db_path: Path = Path("./data/events.db")
    redis_url: str = "redis://localhost:6379/0"
    redis_channel: str = "intellidog:events"
    llm_api_key: str = ""
    llm_model: str = "claude-sonnet-4-6"
    llm_interval_seconds: int = 60
    llm_enabled: bool = True
    compaction_days: int = 30
    log_level: str = "INFO"
    host: str = "0.0.0.0"
    port: int = 8000
    rules_dir: Path = Path("./rules")

    @field_validator("db_path", "rules_dir", mode="before")
    @classmethod
    def coerce_path(cls, v: object) -> Path:
        """Coerce string values to Path."""
        return Path(str(v))


_settings: Settings | None = None


def get_settings() -> Settings:
    """Return the cached Settings singleton."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
