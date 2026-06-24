import re
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.schemas.common import strip_optional_phone, validate_phone_format

NAME_PATTERN = re.compile(r"^[A-Za-z가-힣]+(?:[ A-Za-z가-힣]*[A-Za-z가-힣])?$")


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=100)
    phone: str | None = Field(default=None, max_length=30)

    model_config = ConfigDict(extra="forbid")

    @field_validator("email")
    @classmethod
    def normalize_email(cls, email: EmailStr) -> str:
        return str(email).lower()

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, name: Any) -> Any:
        if not isinstance(name, str):
            return name
        return name.strip()

    @field_validator("phone", mode="before")
    @classmethod
    def strip_phone(cls, phone: Any) -> Any:
        return strip_optional_phone(phone)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, phone: str | None) -> str | None:
        return validate_phone_format(phone)


class SignupResponse(BaseModel):
    id: UUID
    email: EmailStr
    name: str
    phone: str | None
    email_verified_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)

    model_config = ConfigDict(extra="forbid")

    @field_validator("email")
    @classmethod
    def normalize_email(cls, email: EmailStr) -> str:
        return str(email).lower()


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class OAuthProviderLoginRequest(BaseModel):
    code: str = Field(min_length=1, max_length=2048)
    redirect_uri: str = Field(min_length=1, max_length=512)

    model_config = ConfigDict(extra="forbid")

    @field_validator("code", "redirect_uri", mode="before")
    @classmethod
    def strip_oauth_value(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value
        return value.strip()


class KakaoOAuthLoginRequest(OAuthProviderLoginRequest):
    pass


class NaverOAuthLoginRequest(OAuthProviderLoginRequest):
    pass


class OAuthLoginResponse(BaseModel):
    signup_required: bool
    access_token: str | None = None
    token_type: str = "bearer"
    signup_token: str | None = None
    provider: str | None = None
    suggested_email: str | None = None
    suggested_name: str | None = None


class OAuthCompleteSignupRequest(BaseModel):
    signup_token: str = Field(min_length=1, max_length=2048)
    email: EmailStr
    name: str = Field(min_length=1, max_length=100)

    model_config = ConfigDict(extra="forbid")

    @field_validator("signup_token", "name", mode="before")
    @classmethod
    def strip_complete_signup_value(cls, value: Any) -> Any:
        if not isinstance(value, str):
            return value
        return value.strip()

    @field_validator("email")
    @classmethod
    def normalize_complete_signup_email(cls, email: EmailStr) -> str:
        return str(email).lower()

    @field_validator("name")
    @classmethod
    def validate_complete_signup_name(cls, name: str) -> str:
        if not NAME_PATTERN.fullmatch(name):
            raise ValueError("Name can contain only Korean or English letters.")
        return name


class EmailVerificationRequestResponse(BaseModel):
    expires_at: datetime
    verification_url: str | None = None


class EmailVerificationConfirmRequest(BaseModel):
    token: str = Field(min_length=1, max_length=256)

    model_config = ConfigDict(extra="forbid")

    @field_validator("token", mode="before")
    @classmethod
    def strip_token(cls, token: Any) -> Any:
        if not isinstance(token, str):
            return token
        return token.strip()


class EmailVerificationConfirmResponse(BaseModel):
    email_verified_at: datetime


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=8, max_length=128)

    model_config = ConfigDict(extra="forbid")
