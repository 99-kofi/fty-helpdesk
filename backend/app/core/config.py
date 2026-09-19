import os
from pathlib import Path
from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings

# Absolute path: backend/.env loads no matter where uvicorn is launched from.
ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"


class Settings(BaseSettings):
    # Vercel Marketplace integrations conventionally expose POSTGRES_URL. Prefer
    # DATABASE_URL when supplied, while keeping SQLite as the local-only default.
    database_url: str = os.getenv("POSTGRES_URL", "sqlite:///./fty.db")
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 120
    cors_origins: list[str] = ["http://localhost:5173"]
    # The predictable local administrator must never be creatable on a deployed app.
    # setup.ps1 enables this only in the generated local backend/.env.
    allow_default_admin_bootstrap: bool = False

    meta_verify_token: str = "change-me"
    meta_app_secret: str = "change-me"
    meta_api_version: str = "v21.0"
    meta_app_id: str = ""
    meta_page_token: str = "change-me"  # fallback for Instagram/Facebook sends
    meta_oauth_redirect_base: str = "http://localhost:8000"
    frontend_url: str = "http://localhost:5173"
    token_encryption_key: str = ""  # else derived from jwt_secret
    sla_first_response_minutes: int = 30
    sla_resolution_hours: int = 24
    sla_check_minutes: int = 5
    whatsapp_token: str = "change-me"
    whatsapp_phone_number_id: str = ""

    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "support@fty.local"
    smtp_use_tls: bool = True

    # Vercel may inject env vars as empty strings — coerce "" → defaults
    @field_validator(
        "jwt_expire_minutes", "smtp_port",
        "sla_first_response_minutes", "sla_resolution_hours", "sla_check_minutes",
        mode="before",
    )
    @classmethod
    def _empty_to_int(cls, v, info):
        if v == "" or v is None:
            defaults = {
                "jwt_expire_minutes": 120,
                "smtp_port": 587,
                "sla_first_response_minutes": 30,
                "sla_resolution_hours": 24,
                "sla_check_minutes": 5,
            }
            return defaults.get(info.field_name, v)
        return v

    @field_validator("smtp_use_tls", mode="before")
    @classmethod
    def _empty_to_bool(cls, v):
        if v == "" or v is None:
            return True
        if isinstance(v, str):
            if v.lower() in ("true", "1", "yes", "on"):
                return True
            if v.lower() in ("false", "0", "no", "off"):
                return False
        return v

    @field_validator("database_url", "redis_url", mode="before")
    @classmethod
    def _empty_to_default_url(cls, v, info):
        if v == "":
            defaults = {
                "database_url": "sqlite:///./fty.db",
                "redis_url": "redis://localhost:6379/0",
            }
            return defaults.get(info.field_name, v)
        return v

    @field_validator("database_url", mode="after")
    @classmethod
    def _postgres_driver(cls, v: str) -> str:
        """Make standard provider URLs use the installed psycopg v3 driver."""
        if v.startswith("postgres://"):
            return "postgresql+psycopg://" + v.removeprefix("postgres://")
        if v.startswith("postgresql://"):
            return "postgresql+psycopg://" + v.removeprefix("postgresql://")
        return v

    @model_validator(mode="after")
    def _require_persistent_vercel_database(self):
        if os.getenv("VERCEL") and self.database_url.startswith("sqlite"):
            raise ValueError(
                "DATABASE_URL (or POSTGRES_URL) must point to managed PostgreSQL on Vercel; "
                "SQLite is not persistent in Vercel Functions."
            )
        return self

    class Config:
        env_file = str(ENV_FILE)
        extra = "ignore"


settings = Settings()
