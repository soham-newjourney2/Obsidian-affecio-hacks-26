from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[3]
PLACEHOLDER_SECRET = "change-me-to-at-least-32-random-bytes"  # noqa: S105 (the .env.example value)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: Literal["development", "test", "production"] = "development"
    log_level: str = "INFO"
    frontend_dir: Path = ROOT_DIR / "frontend"

    secret_key: SecretStr
    access_token_minutes: int = Field(default=60, ge=1, le=24 * 60)
    database_url: str = "sqlite+aiosqlite:///./echo.db"
    # Attempts per window (register: per IP per hour; login: per IP+email per 15 min).
    register_rate_limit: int = Field(default=5, ge=1)
    login_rate_limit: int = Field(default=10, ge=1)

    # AI companions may fill empty seats only in demo mode.
    demo_mode: bool = False
    admin_emails: str = ""  # comma-separated; these accounts can read reports

    # Optional Jitsi as a Service integration; all signing stays server-side.
    enable_voice_video: bool = False
    jaas_app_id: str = ""
    jaas_key_id: str = ""
    jaas_private_key_path: Path | None = None

    @property
    def media_enabled(self) -> bool:
        return bool(
            self.enable_voice_video
            and self.jaas_app_id
            and self.jaas_key_id
            and self.jaas_private_key_path
        )

    @property
    def admins(self) -> set[str]:
        return {e.strip().lower() for e in self.admin_emails.split(",") if e.strip()}

    # AI: "mock" for tests/offline; "chain" = Groq -> Gemini -> authored fallback.
    ai_provider: Literal["mock", "chain"] = "mock"
    groq_api_key: SecretStr | None = None
    groq_model: str = ""
    gemini_api_key: SecretStr | None = None  # failover only: free tier may train on inputs
    gemini_model: str = ""
    ai_timeout_s: float = Field(default=8.0, gt=0, le=60)
    ai_max_output_tokens: int = Field(default=400, ge=16, le=4096)
    ai_max_calls_per_session: int = Field(default=30, ge=0)

    @field_validator("secret_key")
    @classmethod
    def _secret_long_enough(cls, v: SecretStr) -> SecretStr:
        if len(v.get_secret_value().encode()) < 32:
            raise ValueError("SECRET_KEY must be at least 32 bytes")
        return v

    @field_validator("database_url")
    @classmethod
    def _async_driver(cls, v: str) -> str:
        """Hosted Postgres URLs (postgres://, postgresql://) use the async asyncpg driver."""
        for prefix in ("postgres://", "postgresql://"):
            if v.startswith(prefix):
                return "postgresql+asyncpg://" + v.removeprefix(prefix)
        return v

    @model_validator(mode="after")
    def _no_placeholder_in_production(self) -> "Settings":
        is_placeholder = self.secret_key.get_secret_value() == PLACEHOLDER_SECRET
        if self.app_env == "production" and is_placeholder:
            raise ValueError("SECRET_KEY is still the .env.example placeholder")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
