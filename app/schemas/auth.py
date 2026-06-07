from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=100)
    phone: str | None = Field(default=None, max_length=30)

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
        if phone is None:
            return None
        if not isinstance(phone, str):
            return phone
        phone = phone.strip()
        return phone or None


class SignupResponse(BaseModel):
    id: UUID
    email: EmailStr
    name: str
    phone: str | None
    email_verified_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
