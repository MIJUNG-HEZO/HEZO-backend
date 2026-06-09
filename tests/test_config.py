import pytest
from pydantic import ValidationError

from app.core.config import Settings

VALID_PROD_SECRET = "x" * 32


def make_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "APP_ENV": "local",
        "DATABASE_URL": "postgresql+asyncpg://user:password@localhost:5432/hezo",
        "JWT_SECRET_KEY": VALID_PROD_SECRET,
    }
    values.update(overrides)
    return Settings(**values)


def test_local_environment_allows_short_jwt_secret() -> None:
    settings = make_settings(APP_ENV="local", JWT_SECRET_KEY="short")

    assert settings.is_production is False


def test_production_rejects_short_jwt_secret() -> None:
    with pytest.raises(ValidationError):
        make_settings(APP_ENV="production", JWT_SECRET_KEY="short", COOKIE_SECURE=True)


def test_production_rejects_insecure_cookie() -> None:
    with pytest.raises(ValidationError):
        make_settings(APP_ENV="production", COOKIE_SECURE=False)


def test_production_accepts_secure_configuration() -> None:
    settings = make_settings(APP_ENV="production", COOKIE_SECURE=True)

    assert settings.is_production is True


def test_rejects_unsupported_jwt_algorithm() -> None:
    with pytest.raises(ValidationError):
        make_settings(JWT_ALGORITHM="none")


def test_cors_allowed_origin_list_is_parsed_and_trimmed() -> None:
    settings = make_settings(
        CORS_ALLOWED_ORIGINS="https://a.example.com, https://b.example.com ,",
    )

    assert settings.cors_allowed_origin_list == [
        "https://a.example.com",
        "https://b.example.com",
    ]
