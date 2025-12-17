from __future__ import annotations

import os
from datetime import timedelta
from pathlib import Path


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SQLITE_PATH = BASE_DIR / "db" / "ctfad.db"
DEFAULT_SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)
DEFAULT_SQLALCHEMY_URI = f"sqlite:///{DEFAULT_SQLITE_PATH.as_posix()}"


class Config:
    SQLALCHEMY_DATABASE_URI = os.getenv("DATABASE_URL") or DEFAULT_SQLALCHEMY_URI
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret-key")
    ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "change-me")
    FLAG_LENGTH = int(os.getenv("FLAG_LENGTH", 32))
    FLAG_PREFIX = os.getenv("FLAG_PREFIX", "HHFADCTF{")
    FLAG_SUFFIX = os.getenv("FLAG_SUFFIX", "}")
    FLAG_POINTS = int(os.getenv("FLAG_POINTS", 100))
    SLA_POINTS = int(os.getenv("SLA_POINTS", 25))
    DEFAULT_TICK_LENGTH = int(os.getenv("DEFAULT_TICK_LENGTH", 60))
    DEFAULT_NUM_TICKS = int(os.getenv("DEFAULT_NUM_TICKS", 24))
    DEFAULT_EVENT_DURATION = timedelta(hours=int(os.getenv("DEFAULT_EVENT_HOURS", 12)))
    FLAG_ROTATION_INTERVAL = int(os.getenv("FLAG_ROTATION_INTERVAL", DEFAULT_TICK_LENGTH))
    TIMEZONE = os.getenv("TZ", "UTC")
    AUTO_FLAG_ROTATION = _env_bool("AUTO_FLAG_ROTATION", True)
    AUTO_SLA_CHECKS = _env_bool("AUTO_SLA_CHECKS", True)
    SLA_TICK_LENGTH = int(os.getenv("SLA_TICK_LENGTH", DEFAULT_TICK_LENGTH))
    SLA_PRECHECK_OFFSET = int(os.getenv("SLA_PRECHECK_OFFSET", 20))
