from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-120b"
    gemini_api_key: str = ""
    openrouter_api_key: str = ""
    default_model: str = ""

    firebase_database_url: str = ""
    people_path: str = "users"
    cache_ms: int = 20000

    port: int = 3000
    rate_limit_per_minute: int = 15
    cors_origins: str = "*"
    enable_fallback: bool = True
    log_level: str = "INFO"

    @property
    def cors_origin_list(self) -> list[str]:
        items = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        return items or ["*"]


@lru_cache
def get_settings() -> Settings:
    return Settings()