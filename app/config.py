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
    firebase_api_key: str = ""
    people_path: str = "users"
    instructions_path: str = "ai_instructions"
    cache_ms: int = 20000

    rate_limit_per_minute: int = 15
    cors_origins: str = "*"
    enable_fallback: bool = True
    log_level: str = "INFO"

    upstash_redis_rest_url: str = ""
    upstash_redis_rest_token: str = ""
    kv_rest_api_url: str = ""
    kv_rest_api_token: str = ""

    @property
    def redis_url(self) -> str:
        return (self.upstash_redis_rest_url or self.kv_rest_api_url).rstrip("/")

    @property
    def redis_token(self) -> str:
        return self.upstash_redis_rest_token or self.kv_rest_api_token

    @property
    def cors_origin_list(self) -> list[str]:
        items = [o.strip() for o in self.cors_origins.split(",") if o.strip()]
        return items or ["*"]


@lru_cache
def get_settings() -> Settings:
    return Settings()