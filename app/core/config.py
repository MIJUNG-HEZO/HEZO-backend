from functools import lru_cache
from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parents[2]

DEVELOPMENT_ENVIRONMENTS = frozenset({"local", "dev", "test"})
# staging은 운영과 동일한 보안 기준(쿠키 보안·비밀값 검증)과 문서 비공개를 적용하기 위해
# 운영 환경군으로 분류한다. 운영 배포 전 검증 환경이므로 fail-closed를 우선한다.
PRODUCTION_ENVIRONMENTS = frozenset({"staging", "production", "prod"})
SUPPORTED_JWT_ALGORITHMS = frozenset({"HS256", "HS384", "HS512"})
JWT_SECRET_MIN_LENGTH = 32


class Settings(BaseSettings):
    app_env: str = Field(default="local", alias="APP_ENV")
    app_name: str = Field(default="HEZO API", alias="APP_NAME")
    api_v1_prefix: str = Field(default="/api/v1", alias="API_V1_PREFIX")
    cors_allowed_origins: str = Field(
        default="http://localhost:3000,http://localhost:3001",
        alias="CORS_ALLOWED_ORIGINS",
    )
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
    naver_client_id: str = Field(default="", alias="NAVER_CLIENT_ID")
    naver_client_secret: str = Field(default="", alias="NAVER_CLIENT_SECRET")
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
    p1_agent_endpoint: str | None = Field(default=None, alias="P1_AGENT_ENDPOINT")
    p1_agentcore_runtime_arn: str | None = Field(default=None, alias="P1_AGENTCORE_RUNTIME_ARN")
    p3_build_endpoint: str | None = Field(default=None, alias="P3_BUILD_ENDPOINT")
    obs_prometheus_url: str = Field(default="", alias="OBS_PROMETHEUS_URL")
    redis_url: str = Field(default="redis://localhost:6379/0", alias="REDIS_URL")
    redis_enabled: bool = Field(default=False, alias="REDIS_ENABLED")

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    @property
    def is_production(self) -> bool:
        return self.app_env in PRODUCTION_ENVIRONMENTS

    @property
    def cors_allowed_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]

    @model_validator(mode="after")
    def validate_jwt_algorithm(self) -> "Settings":
        if self.jwt_algorithm not in SUPPORTED_JWT_ALGORITHMS:
            raise ValueError(
                f"JWT_ALGORITHM must be one of {sorted(SUPPORTED_JWT_ALGORITHMS)}."
            )
        return self

    @model_validator(mode="after")
    def validate_production_security(self) -> "Settings":
        if not self.is_production:
            return self

        if len(self.jwt_secret) < JWT_SECRET_MIN_LENGTH:
            raise ValueError(
                f"JWT_SECRET_KEY must be at least {JWT_SECRET_MIN_LENGTH} characters "
                "in production environments."
            )
        if not self.refresh_token_cookie_secure:
            raise ValueError("COOKIE_SECURE must be true in production environments.")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
