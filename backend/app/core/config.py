"""Application settings, read from environment variables and `backend/.env`."""

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL, make_url

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # A full URL takes precedence over the separate DB_* fields.
    database_url: SecretStr | None = None
    db_host: str = "127.0.0.1"
    db_port: int = 5432
    db_name: str | None = None
    db_user: str | None = None
    db_password: SecretStr | None = None
    # Hosted databases (e.g. Supabase) need an encrypted connection: set to "require".
    db_sslmode: Literal["disable", "prefer", "require", "verify-ca", "verify-full"] | None = None
    # Connection pool. On serverless hosts (Vercel) every running copy of the API keeps its own
    # pool, and a free database allows few connections in total: use a small pool there.
    db_pool_size: int = 5
    db_max_overflow: int = 10

    # Comma-separated list of browser origins allowed by CORS.
    frontend_origins: str = "http://localhost:3000,http://localhost:3001"

    # "production" turns on secure cookies and hides the interactive API docs.
    app_env: Literal["development", "production"] = "development"
    # Optional code required to create the FIRST account through the website. Set it
    # on a public deployment so a stranger cannot claim the owner account.
    setup_code: SecretStr | None = None
    # Email (SMTP), used to send sign-up verification codes. When it is not configured, accounts
    # are created without verification and public sign-up stays closed (only the owner account).
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: SecretStr | None = None
    smtp_from: str | None = None  # defaults to smtp_user (Gmail only sends as the account itself)
    smtp_security: Literal["starttls", "ssl", "none"] = "starttls"
    # Alternative to SMTP: Brevo's HTTPS API (works on hosts such as Vercel that cannot reach SMTP
    # servers). `mail_from` must be a sender address verified in your Brevo account.
    brevo_api_key: SecretStr | None = None
    mail_from: str | None = None
    # Lets anyone with a real email address create an account (only works with email configured).
    allow_signup: bool = True
    session_cookie_name: str = "ciq_session"
    session_hours: int = 24            # login without "remember me"
    remember_session_days: int = 30    # login with "remember me"

    @property
    def cookie_secure(self) -> bool:
        return self.app_env == "production"

    @property
    def email_configured(self) -> bool:
        sender = self.mail_from or self.smtp_from or self.smtp_user
        has_password = bool(self.smtp_password and self.smtp_password.get_secret_value().strip())
        has_api_key = bool(self.brevo_api_key and self.brevo_api_key.get_secret_value().strip())
        return bool(sender and (has_api_key or (self.smtp_host and has_password)))

    @property
    def email_verification_required(self) -> bool:
        """New accounts must confirm their email with a code (needs email to be set up)."""
        return self.email_configured

    @property
    def signup_open(self) -> bool:
        return self.email_verification_required and self.allow_signup

    @property
    def setup_code_required(self) -> bool:
        return bool(self.setup_code and self.setup_code.get_secret_value().strip())

    # AI assistant (server-side only; never exposed to the browser).
    # Provider: "anthropic" (Claude, default) or "openai".
    ai_provider: Literal["anthropic", "openai"] = "anthropic"
    anthropic_api_key: SecretStr | None = None
    anthropic_model: str = "claude-opus-5-5"
    openai_api_key: SecretStr | None = None
    openai_model: str = "gpt-6-luna"
    assistant_timeout_seconds: float = 60.0

    @property
    def assistant_api_key(self) -> SecretStr | None:
        return self.anthropic_api_key if self.ai_provider == "anthropic" else self.openai_api_key

    @property
    def assistant_model(self) -> str:
        return self.anthropic_model if self.ai_provider == "anthropic" else self.openai_model

    @property
    def assistant_configured(self) -> bool:
        key = self.assistant_api_key
        return bool(key and key.get_secret_value().strip())

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.frontend_origins.split(",") if o.strip()]

    @property
    def database_configured(self) -> bool:
        # A blank DATABASE_URL counts as "not set", so the separate DB_* fields are used.
        if self.database_url is not None and self.database_url.get_secret_value().strip():
            return True
        return bool(self.db_name and self.db_user and self.db_password)

    def sqlalchemy_url(self) -> URL:
        """Build the connection URL. Its repr/str masks the password."""
        if self.database_url is not None and self.database_url.get_secret_value().strip():
            url = make_url(self.database_url.get_secret_value().strip())
            # Hosts hand out "postgresql://..."; this app uses the psycopg 3 driver.
            if url.drivername in ("postgresql", "postgres"):
                url = url.set(drivername="postgresql+psycopg")
            return url
        if not self.database_configured:
            raise DatabaseNotConfiguredError()
        assert self.db_password is not None
        return URL.create(
            "postgresql+psycopg",
            username=self.db_user,
            password=self.db_password.get_secret_value(),
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
            query={"sslmode": self.db_sslmode} if self.db_sslmode else {},
        )


class DatabaseNotConfiguredError(RuntimeError):
    def __init__(self) -> None:
        super().__init__(
            "Database is not configured. Set DB_NAME, DB_USER and DB_PASSWORD "
            "(or DATABASE_URL) in backend/.env."
        )


@lru_cache
def get_settings() -> Settings:
    return Settings()
