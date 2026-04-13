from pydantic_settings import BaseSettings
from pydantic import field_validator, PostgresDsn
from typing import List
import secrets


class Settings(BaseSettings):
    # ── App ──────────────────────────────────────────────────────────────────
    app_env: str = "development"
    app_version: str = "0.1.0"
    enforce_https: bool = False

    # ── Database ─────────────────────────────────────────────────────────────
    database_url: str
    test_database_url: str = ""

    # ── Anthropic ────────────────────────────────────────────────────────────
    anthropic_api_key: str

    # ── JWT ──────────────────────────────────────────────────────────────────
    secret_key: str
    refresh_secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 60
    refresh_token_expire_days: int = 7

    # ── CORS ─────────────────────────────────────────────────────────────────
    allowed_origins: str = "http://localhost:5173"

    # ── Rate Limiting ────────────────────────────────────────────────────────
    rate_limit_per_minute: int = 30
    rate_limit_analyze_per_minute: int = 10

    @field_validator("secret_key", "refresh_secret_key")
    @classmethod
    def validate_secret_strength(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("Secret keys must be at least 32 characters long.")
        return v

    @field_validator("anthropic_api_key")
    @classmethod
    def validate_api_key(cls, v: str) -> str:
        if not v.startswith("sk-ant-"):
            raise ValueError("ANTHROPIC_API_KEY must start with 'sk-ant-'")
        return v

    @property
    def origins_list(self) -> List[str]:
        return [o.strip() for o in self.allowed_origins.split(",")]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    class Config:
        env_file = ".env"
        case_sensitive = False


settings = Settings()
