"""Settings."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    prometheus_url: str = "http://prometheus:9090"
    ai_gateway_url: str = "http://ai-gateway:8080"
    gateway_shared_secret: str
    interval_hours: int = 6
    host_cpu_cores: int = 8
    host_ram_gb: int = 32
    host_disk_gb: int = 500
    output_dir: Path = Path("/data")
    log_level: str = "info"


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
