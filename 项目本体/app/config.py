from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str = "sqlite:///./data/ai_radar.db"
    demo_mode: bool = True
    rss_urls: str = ""
    github_token: str | None = None
    x_bearer_token: str | None = None
    comfyui_url: str | None = None
    collection_interval_minutes: int = 60
    scheduler_enabled: bool = True
    draft_generator_provider: str = "template"

    model_config = SettingsConfigDict(
        env_file=PROJECT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
