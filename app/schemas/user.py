import re
from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

NAME_PATTERN = re.compile(r"^[A-Za-z가-힣]+( [A-Za-z가-힣]+)*$")
PHONE_PATTERN = re.compile(r"^[0-9+\- ()]{7,30}$")


class UserResponse(BaseModel):
    id: UUID
    email: EmailStr
    name: str
    phone: str | None
    email_verified_at: datetime | None
    email_verified: bool
    created_at: datetime
    updated_at: datetime


class UserUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    phone: str | None = Field(default=None, max_length=30)

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
        if phone is None:
            return None
        if not isinstance(phone, str):
            return phone
        phone = phone.strip()
        return phone or None

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, phone: str | None) -> str | None:
        if phone is None:
            return None
        if not PHONE_PATTERN.fullmatch(phone):
            raise ValueError("Phone number format is invalid.")
        return phone


class UserModelResponse(BaseModel):
    id: UUID
    email: EmailStr
    name: str
    phone: str | None
    email_verified_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
