from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_env: str = Field(default="local", alias="APP_ENV")
    app_name: str = Field(default="HEZO API", alias="APP_NAME")
    api_v1_prefix: str = Field(default="/api/v1", alias="API_V1_PREFIX")
    database_url: str = Field(alias="DATABASE_URL")
    jwt_secret: str = Field(alias="JWT_SECRET_KEY")
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    access_token_expires_minutes: int = Field(
        default=15,
        alias="ACCESS_TOKEN_EXPIRE_MINUTES",
    )
    refresh_token_expires_days: int = Field(
        default=14,
        alias="REFRESH_TOKEN_EXPIRE_DAYS",
    )
    refresh_token_cookie_name: str = Field(
        default="refresh_token",
        alias="REFRESH_TOKEN_COOKIE_NAME",
    )
    refresh_token_cookie_secure: bool = Field(
        default=False,
        alias="COOKIE_SECURE",
    )
    frontend_base_url: str = Field(
        default="http://localhost:3000",
        alias="FRONTEND_BASE_URL",
    )
    email_verification_token_expires_minutes: int = Field(
        default=30,
        alias="EMAIL_VERIFICATION_TOKEN_EXPIRE_MINUTES",
    )
    smtp_host: str = Field(default="", alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_username: str = Field(default="", alias="SMTP_USERNAME")
    smtp_password: str = Field(default="", alias="SMTP_PASSWORD")
    smtp_use_tls: bool = Field(default=True, alias="SMTP_USE_TLS")
    smtp_from_email: str = Field(default="", alias="SMTP_FROM_EMAIL")
    kakao_client_id: str = Field(default="", alias="KAKAO_CLIENT_ID")
    kakao_client_secret: str = Field(default="", alias="KAKAO_CLIENT_SECRET")
    oauth_signup_token_expires_minutes: int = Field(
        default=10,
        alias="OAUTH_SIGNUP_TOKEN_EXPIRE_MINUTES",
    )
    toss_payments_client_key: str = Field(default="", alias="TOSS_PAYMENTS_CLIENT_KEY")
    toss_payments_secret_key: str = Field(default="", alias="TOSS_PAYMENTS_SECRET_KEY")
    toss_payments_success_url: str = Field(
        default="http://localhost:3000/billing/success",
        alias="TOSS_PAYMENTS_SUCCESS_URL",
    )
    toss_payments_fail_url: str = Field(
        default="http://localhost:3000/billing/fail",
        alias="TOSS_PAYMENTS_FAIL_URL",
    )

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
