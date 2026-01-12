import os
from urllib.parse import urlparse, unquote

from dotenv import load_dotenv
from typing import Optional

# Load local env files (not committed). Safe in production too: missing files are ignored.
# We prefer `env.local` in this repo (since `.env*` may be globally ignored in some environments).
load_dotenv("env.local")
load_dotenv()


def _get_env(name: str) -> Optional[str]:
    value = os.environ.get(name)
    if value is None:
        return None
    value = value.strip()
    return value if value else None


def get_db_config() -> dict:
    """
    Build psycopg2 connection kwargs.

    Supported configuration:
    - DATABASE_URL=postgresql://user:pass@host:port/dbname
    - or DB_HOST/DB_NAME/DB_USER/DB_PASSWORD/DB_PORT

    Notes:
    - Supabase requires SSL; default is sslmode=require unless overridden with DB_SSLMODE.
    """
    database_url = _get_env("DATABASE_URL")
    sslmode = _get_env("DB_SSLMODE") or "require"

    if database_url:
        parsed = urlparse(database_url)
        if parsed.scheme not in ("postgres", "postgresql"):
            raise ValueError("DATABASE_URL must start with postgres:// or postgresql://")

        host = parsed.hostname
        user = unquote(parsed.username) if parsed.username else None
        password = unquote(parsed.password) if parsed.password else None
        port = parsed.port or 5432
        dbname = parsed.path.lstrip("/") or "postgres"

        missing = [k for k, v in {"host": host, "user": user, "password": password}.items() if not v]
        if missing:
            raise ValueError(f"DATABASE_URL is missing required parts: {', '.join(missing)}")

        return {
            "host": host,
            "database": dbname,
            "user": user,
            "password": password,
            "port": int(port),
            "sslmode": sslmode,
        }

    host = _get_env("DB_HOST")
    dbname = _get_env("DB_NAME") or "postgres"
    user = _get_env("DB_USER") or "postgres"
    password = _get_env("DB_PASSWORD")
    port = int(_get_env("DB_PORT") or "5432")

    if not host or not password:
        raise ValueError("Missing DB config: set DATABASE_URL or DB_HOST + DB_PASSWORD (and optionally DB_NAME/DB_USER/DB_PORT).")

    return {
        "host": host,
        "database": dbname,
        "user": user,
        "password": password,
        "port": port,
        "sslmode": sslmode,
    }


# OpenAI API Keys - environment variables only (no defaults committed)
openaiapi_key = _get_env("OPENAI_API_KEY")
openaiapi_panda_key = _get_env("OPENAI_PANDA_KEY")
azureopenai_key = _get_env("AZURE_OPENAI_KEY")

# Project configuration
panda_project = _get_env("PANDA_PROJECT_ID") or "your_panda_project_id"
default_prompt = _get_env("DEFAULT_PROMPT") or "Default system prompt"
