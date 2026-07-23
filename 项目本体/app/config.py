from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


PROJECT_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    app_env: str = "development"
    database_url: str = "sqlite:///./data/ai_radar.db"
    rss_urls: str = ""
    github_token: str | None = None
    x_bearer_token: str | None = None
    comfyui_url: str | None = None
    collection_interval_minutes: int = 60
    scheduler_enabled: bool = True
    draft_generator_provider: str = "template"
    openai_api_key: str | None = None
    openai_model: str = "gpt-5.6"
    source_weight_arxiv: float = Field(default=1.4, ge=0)
    source_weight_github: float = Field(default=1.2, ge=0)
    source_weight_hacker_news: float = Field(default=0.85, ge=0)
    source_weight_rss: float = Field(default=1.0, ge=0)
    source_weight_x: float = Field(default=1.1, ge=0)
    source_weight_bilibili: float = Field(default=1.0, ge=0)
    source_weight_default: float = Field(default=1.0, ge=0)
    authority_author_bonus: float = Field(default=0.65, ge=0)
    heat_freshness_weight: float = Field(default=1.0, ge=0)
    heat_engagement_weight: float = Field(default=1.0, ge=0)
    x_author_usernames: str = ""
    bilibili_author_mids: str = ""
    trusted_author_names: str = ""

    model_config = SettingsConfigDict(
        env_file=PROJECT_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
