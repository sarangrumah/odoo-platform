"""Settings loaded from environment via pydantic-settings."""

from __future__ import annotations

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # Provider routing
    ai_provider: Literal["anthropic", "openai", "ollama"] = "anthropic"
    ai_model_default: str = "claude-sonnet-4-6"
    ai_model_quality: str = "claude-opus-4-7"

    # API keys
    anthropic_api_key: str | None = None
    openai_api_key: str | None = None
    openai_model_default: str = "gpt-4o"

    # Ollama
    ollama_base_url: str = "http://ollama:11434"
    ollama_model_default: str = "llama3.2:3b"
    ollama_model_quality: str = "qwen2.5:7b"

    # Redis (rate limit + cache)
    redis_url: str = "redis://redis:6379/0"

    # Security
    gateway_shared_secret: str = Field(min_length=32)
    hmac_window_seconds: int = 300  # 5 min replay window
    rate_limit_per_minute: int = 60
    cors_origins: list[str] = Field(default_factory=lambda: ["http://odoo:8069", "http://localhost:18069"])

    # Logging
    log_level: str = "info"

    # Server
    host: str = "0.0.0.0"
    port: int = 8080


_settings: Settings | None = None


def get_settings() -> Settings:
    """Cached settings accessor."""
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
