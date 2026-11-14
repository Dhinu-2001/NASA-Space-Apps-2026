"""Externalised configuration (environment variables prefixed LUNARNAV_, optional .env file)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LUNARNAV_", env_file=".env", extra="ignore")

    env: Literal["development", "production", "test"] = "development"
    log_level: str = "INFO"
    log_json: bool = True
    data_dir: Path = Field(default=REPO_ROOT / "data")
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
