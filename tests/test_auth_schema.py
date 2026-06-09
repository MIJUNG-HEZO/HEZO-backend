import pytest
from pydantic import ValidationError

from app.schemas.auth import SignupRequest

VALID_SIGNUP = {
    "email": "user@example.com",
    "password": "password123",
    "name": "홍길동",
}


def test_signup_request_accepts_valid_phone() -> None:
    request = SignupRequest(**VALID_SIGNUP, phone="010-1234-5678")

    assert request.phone == "010-1234-5678"


def test_signup_request_normalizes_blank_phone_to_none() -> None:
    request = SignupRequest(**VALID_SIGNUP, phone="   ")

    assert request.phone is None


def test_signup_request_rejects_invalid_phone() -> None:
    with pytest.raises(ValidationError):
        SignupRequest(**VALID_SIGNUP, phone="abc!!")


def test_signup_request_rejects_unknown_field() -> None:
    with pytest.raises(ValidationError):
        SignupRequest(**VALID_SIGNUP, is_admin=True)


def test_signup_request_lowercases_email() -> None:
    request = SignupRequest(**{**VALID_SIGNUP, "email": "USER@Example.com"})

    assert request.email == "user@example.com"
