"""Centralised application configuration.

All environment variable reads happen here so the rest of the codebase
works with typed attributes instead of scattered ``os.environ.get()`` calls.
"""

import hashlib
import os
import subprocess
import platform
from dataclasses import dataclass, field
from typing import Optional, Union

import credentials


def _env(name: str, default: str = "") -> str:
    return (os.environ.get(name) or "").strip() or default


def _env_opt(name: str) -> Optional[str]:
    val = (os.environ.get(name) or "").strip()
    return val or None


def _env_int(name: str, default: int, min_v: int = 0, max_v: int = 2**31) -> int:
    raw = _env(name)
    try:
        v = int(raw) if raw else default
    except (ValueError, TypeError):
        v = default
    return max(min_v, min(max_v, v))


def _env_float(name: str, default: float) -> float:
    raw = _env(name)
    try:
        v = float(raw) if raw else default
    except (ValueError, TypeError):
        v = default
    return max(0.0, v)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = _env(name).lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


def _resolve_secret_key() -> Optional[Union[str, bytes]]:
    primary = _env_opt("SECRET_KEY") or _env_opt("FLASK_SECRET_KEY")
    if primary:
        return primary
    fallback = _env_opt("SHARE_LINK_ENC_KEY")
    if fallback:
        return hashlib.sha256(fallback.encode("utf-8")).digest()
    return None


def _resolve_app_version() -> str:
    sha = _env("RAILWAY_GIT_COMMIT_SHA")
    if sha:
        return sha[:7]
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
    except Exception:
        pass
    return "dev"


@dataclass(frozen=True)
class AppConfig:
    # Database
    db_config: dict = field(repr=False)

    # API keys (from credentials module)
    openai_key: Optional[str] = field(default=None, repr=False)
    openai_panda_key: Optional[str] = field(default=None, repr=False)
    azure_key: Optional[str] = field(default=None, repr=False)
    panda_project: str = ""
    default_prompt: str = ""

    # Flask / session
    secret_key: Optional[Union[str, bytes]] = field(default=None, repr=False)
    session_cookie_samesite: str = "Lax"
    session_cookie_secure: bool = False

    # Share links
    share_link_enc_key: Optional[str] = field(default=None, repr=False)
    share_login_rate_window_min: int = 15
    share_login_rate_max_failures: int = 8

    # Admin / internal
    admin_local_key: Optional[str] = field(default=None, repr=False)
    internal_api_key: Optional[str] = field(default=None, repr=False)

    # Voice
    voice_transcription_model: str = "whisper-1"
    voice_max_bytes: int = 15 * 1024 * 1024

    # Session management
    session_inactivity_minutes: int = 10

    # Usage pricing
    token_usd_per_1k: float = 0.01
    audio_usd_per_1k: float = 0.000006

    # Server
    port: int = 5000
    app_version: str = "dev"

    @classmethod
    def from_env(cls) -> "AppConfig":
        return cls(
            db_config=credentials.get_db_config(),
            openai_key=credentials.openaiapi_key,
            openai_panda_key=credentials.openaiapi_panda_key,
            azure_key=credentials.azureopenai_key,
            panda_project=credentials.panda_project,
            default_prompt=credentials.default_prompt,
            secret_key=_resolve_secret_key(),
            session_cookie_samesite=_env("SESSION_COOKIE_SAMESITE", "Lax"),
            session_cookie_secure=_env_bool("SESSION_COOKIE_SECURE"),
            share_link_enc_key=_env_opt("SHARE_LINK_ENC_KEY"),
            share_login_rate_window_min=_env_int("SHARE_LOGIN_RATE_WINDOW_MIN", 15, 1, 1440),
            share_login_rate_max_failures=_env_int("SHARE_LOGIN_RATE_MAX_FAILURES", 8, 1, 10000),
            admin_local_key=_env_opt("ADMIN_LOCAL_KEY"),
            internal_api_key=_env_opt("INTERNAL_API_KEY"),
            voice_transcription_model=_env("VOICE_TRANSCRIPTION_MODEL", "whisper-1"),
            voice_max_bytes=_env_int("VOICE_MAX_BYTES", 15 * 1024 * 1024, min_v=1024),
            session_inactivity_minutes=_env_int("SESSION_INACTIVITY_MINUTES", 10, 1, 1440),
            token_usd_per_1k=_env_float("TOKEN_USD_PER_1K", 0.01),
            audio_usd_per_1k=_env_float("AUDIO_USD_PER_1K", 0.000006),
            port=_env_int("PORT", 5000, 1, 65535),
            app_version=_resolve_app_version(),
        )


cfg = AppConfig.from_env()
