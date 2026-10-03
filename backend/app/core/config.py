from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator, model_validator
from cryptography.fernet import Fernet
from typing import List


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False, extra="ignore")

    # ── App ──────────────────────────────────────────────────────────────────
    app_env: str = "development"
    app_version: str = "0.1.0"
    enforce_https: bool = False

    # ── Database ─────────────────────────────────────────────────────────────
    database_url: str
    test_database_url: str = ""
    database_ssl: bool = False          # require TLS to PostgreSQL

    # ── Anthropic ────────────────────────────────────────────────────────────
    anthropic_api_key: str
    anthropic_model: str = "claude-sonnet-4-20250514"

    # ── JWT ──────────────────────────────────────────────────────────────────
    secret_key: str
    refresh_secret_key: str
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 1
    max_session_hours: int = 12         # absolute session lifetime, refresh can't extend past it
    mfa_token_expire_minutes: int = 5

    # ── Encryption at rest (MFA secrets) ─────────────────────────────────────
    # Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    encryption_key: str

    # ── MFA ──────────────────────────────────────────────────────────────────
    # When true, users without MFA can only enroll until they turn it on.
    require_mfa: bool = False

    # ── CORS ─────────────────────────────────────────────────────────────────
    allowed_origins: str = "http://localhost:5173"

    # ── Proxies ──────────────────────────────────────────────────────────────
    # Comma-separated IPs/CIDRs of reverse proxies whose X-Forwarded-For is trusted.
    trusted_proxies: str = ""

    # ── Rate Limiting ────────────────────────────────────────────────────────
    rate_limit_enabled: bool = True
    rate_limit_storage_uri: str = "memory://"   # use redis://... with multiple workers
    rate_limit_per_minute: int = 60
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

    @field_validator("encryption_key")
    @classmethod
    def validate_encryption_key(cls, v: str) -> str:
        try:
            Fernet(v.encode())
        except Exception:
            raise ValueError("ENCRYPTION_KEY must be a Fernet key (32 url-safe base64-encoded bytes).")
        return v

    @model_validator(mode="after")
    def validate_production(self) -> "Settings":
        if not self.is_production:
            return self
        problems = []
        if self.secret_key == self.refresh_secret_key:
            problems.append("SECRET_KEY and REFRESH_SECRET_KEY must differ")
        if not self.enforce_https:
            problems.append("ENFORCE_HTTPS must be true")
        if not self.database_ssl:
            problems.append("DATABASE_SSL must be true")
        if any("localhost" in o or "127.0.0.1" in o or o == "*" for o in self.origins_list):
            problems.append("ALLOWED_ORIGINS must not include localhost or '*'")
        if problems:
            raise ValueError("Unsafe production configuration: " + "; ".join(problems))
        return self

    @property
    def origins_list(self) -> List[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def trusted_proxies_list(self) -> List[str]:
        return [p.strip() for p in self.trusted_proxies.split(",") if p.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def secure_cookies(self) -> bool:
        return self.is_production or self.enforce_https


settings = Settings()
