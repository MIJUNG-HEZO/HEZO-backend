import re
from typing import Any

PHONE_PATTERN = re.compile(r"^[0-9+\- ()]{7,30}$")


def strip_optional_phone(phone: Any) -> Any:
    if phone is None:
        return None
    if not isinstance(phone, str):
        return phone
    phone = phone.strip()
    return phone or None


def validate_phone_format(phone: str | None) -> str | None:
    if phone is None:
        return None
    if not PHONE_PATTERN.fullmatch(phone):
        raise ValueError("Phone number format is invalid.")
    return phone
