"""Application configuration loaded from environment variables."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class DatabaseConfig:
    """PostgreSQL connection settings."""

    url: str
    pool_min_size: int
    pool_max_size: int
    statement_timeout_ms: int
    idle_timeout_ms: int


@dataclass(frozen=True, slots=True)
class EncryptionConfig:
    """Fernet encryption settings."""

    key: str


@dataclass(frozen=True, slots=True)
class Settings:
    """Top-level application settings."""

    database: DatabaseConfig
    encryption: EncryptionConfig


def _require_env(name: str) -> str:
    """Read a required environment variable or raise."""
    value = os.environ.get(name)
    if not value:
        msg = f"Required environment variable {name} is not set"
        raise OSError(msg)
    return value


def _env_int(name: str, default: int) -> int:
    """Read an optional integer environment variable."""
    raw = os.environ.get(name)
    return int(raw) if raw is not None else default


def load_settings() -> Settings:
    """Build Settings from environment variables."""
    db = DatabaseConfig(
        url=_require_env("SACP_DATABASE_URL"),
        pool_min_size=_env_int("POOL_MIN_SIZE", 2),
        pool_max_size=_env_int("POOL_MAX_SIZE", 10),
        statement_timeout_ms=_env_int("STATEMENT_TIMEOUT_MS", 30_000),
        idle_timeout_ms=_env_int("IDLE_TIMEOUT_MS", 60_000),
    )
    enc = EncryptionConfig(key=_require_env("SACP_ENCRYPTION_KEY"))
    return Settings(database=db, encryption=enc)
