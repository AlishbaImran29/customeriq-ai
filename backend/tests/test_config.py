import pytest

from app.core.config import DatabaseNotConfiguredError, Settings


def make_settings(**values) -> Settings:
    # _env_file=None: ignore any real backend/.env during tests.
    return Settings(_env_file=None, **values)


def test_not_configured_without_credentials():
    settings = make_settings()
    assert settings.database_configured is False
    with pytest.raises(DatabaseNotConfiguredError):
        settings.sqlalchemy_url()


def test_url_built_from_fields_escapes_special_characters():
    settings = make_settings(
        db_name="customeriq", db_user="customeriq_app", db_password="p@ss:w/rd%#"
    )
    url = settings.sqlalchemy_url()
    assert url.drivername == "postgresql+psycopg"
    assert url.password == "p@ss:w/rd%#"
    assert url.host == "127.0.0.1" and url.port == 5432 and url.database == "customeriq"


def test_password_never_appears_in_str_or_repr():
    settings = make_settings(db_name="db", db_user="user", db_password="s3cret-value")
    assert "s3cret-value" not in str(settings.sqlalchemy_url())
    assert "s3cret-value" not in repr(settings)


def test_database_url_overrides_fields():
    settings = make_settings(
        database_url="postgresql+psycopg://u:pw@db.example:6543/prod",
        db_name="ignored", db_user="ignored", db_password="ignored",
    )
    url = settings.sqlalchemy_url()
    assert (url.host, url.port, url.database) == ("db.example", 6543, "prod")


def test_cors_origins_parsed_from_comma_list():
    settings = make_settings(frontend_origins=" http://a.test , http://b.test ,")
    assert settings.cors_origins == ["http://a.test", "http://b.test"]
