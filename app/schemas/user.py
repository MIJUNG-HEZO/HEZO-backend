import re
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.schemas.common import strip_optional_phone, validate_phone_format

NAME_PATTERN = re.compile(r"^[A-Za-z가-힣]+( [A-Za-z가-힣]+)*$")


class UserResponse(BaseModel):
    id: UUID
    email: EmailStr
    name: str
    phone: str | None
    email_verified_at: datetime | None
    email_verified: bool
    role: str
    created_at: datetime
    updated_at: datetime


class UserUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    phone: str | None = Field(default=None, max_length=30)

    model_config = ConfigDict(extra="forbid")

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, name: Any) -> Any:
        if not isinstance(name, str):
            return name
        return name.strip()

    @field_validator("name")
    @classmethod
    def validate_name(cls, name: str | None) -> str | None:
        if name is None:
            return None
        if not NAME_PATTERN.fullmatch(name):
            raise ValueError("Name can contain only Korean or English letters.")
        return name

    @field_validator("phone", mode="before")
    @classmethod
    def strip_phone(cls, phone: Any) -> Any:
        return strip_optional_phone(phone)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, phone: str | None) -> str | None:
        return validate_phone_format(phone)


class UserModelResponse(BaseModel):
    id: UUID
    email: EmailStr
    name: str
    phone: str | None
    email_verified_at: datetime | None
    role: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
