from pathlib import Path
from pydantic_settings import BaseSettings

# Absolute path: backend/.env loads no matter where uvicorn is launched from.
ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"


class Settings(BaseSettings):
    database_url: str = "sqlite:///./fty.db"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 120
    cors_origins: list[str] = ["http://localhost:5173"]

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

    class Config:
        env_file = str(ENV_FILE)
        extra = "ignore"


settings = Settings()
