"""Application settings, read from environment variables and `backend/.env`."""

from functools import lru_cache
from pathlib import Path

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

    # Comma-separated list of browser origins allowed by CORS.
    frontend_origins: str = "http://localhost:3000,http://localhost:3001"

    @property
    def cors_origins(self) -> list[str]:
        return [o.strip() for o in self.frontend_origins.split(",") if o.strip()]

    @property
    def database_configured(self) -> bool:
        if self.database_url is not None:
            return bool(self.database_url.get_secret_value().strip())
        return bool(self.db_name and self.db_user and self.db_password)

    def sqlalchemy_url(self) -> URL:
        """Build the connection URL. Its repr/str masks the password."""
        if self.database_url is not None and self.database_url.get_secret_value().strip():
            return make_url(self.database_url.get_secret_value().strip())
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
