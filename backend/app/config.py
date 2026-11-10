"""Application settings, read from environment variables (see ``.env.example``)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=REPO_ROOT / ".env", extra="ignore")

    # Storage
    database_url: str = f"sqlite:///{REPO_ROOT / 'bvmt.db'}"
    data_parquet: Path = REPO_ROOT / "data" / "bvmt_prices.parquet"

    # HTTP
    cors_origins: str = "http://localhost:3000"

    # Auth. An empty secret means "generate one at start-up" (tokens then stop
    # being valid when the process restarts).
    jwt_secret: str = ""
    access_token_minutes: int = 60 * 24

    # One OpenAI-compatible LLM endpoint for every LLM feature. Optional.
    llm_base_url: str = "https://api.openai.com/v1"
    llm_api_key: str = ""
    llm_model: str = "gpt-4o-mini"
    llm_timeout_seconds: float = 30.0

    # Live news scraping is opt-in.
    enable_scraping: bool = False
    news_feeds: str = (
        "https://www.webdo.tn/fr/feed/,https://kapitalis.com/tunisie/feed/,https://africanmanager.com/feed/"
    )
    scrape_timeout_seconds: float = 8.0

    # Finance assumptions
    risk_free_rate: float = 0.07  # annual, close to the Tunisian money-market rate

    # E-mail (optional). Without SMTP_HOST, messages are kept in the outbox only.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "bvmt-assistant@localhost"
    smtp_starttls: bool = True

    # Background jobs (daily anomaly scan, e-mail alerts, market report)
    enable_scheduler: bool = False
    scheduler_interval_minutes: int = 60 * 24

    @property
    def sqlalchemy_url(self) -> str:
        url = self.database_url
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://") :]
        if url.startswith("postgresql://"):
            url = "postgresql+psycopg://" + url[len("postgresql://") :]
        return url

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def news_feed_list(self) -> list[str]:
        return [u.strip() for u in self.news_feeds.split(",") if u.strip()]

    @property
    def llm_configured(self) -> bool:
        return bool(self.llm_api_key.strip())


@lru_cache
def get_settings() -> Settings:
    return Settings()
