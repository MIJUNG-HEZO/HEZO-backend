import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.api.deps import get_auth_service
from app.core import error_codes
from app.core.exceptions import AppException
from app.main import app
from app.schemas.auth import SignupRequest, SignupResponse
from app.services.auth_service import AuthService
from app.services.password_service import PasswordService


class FakeAuthService:
    def __init__(self) -> None:
        self.payload: SignupRequest | None = None

    async def signup(self, payload: SignupRequest) -> SignupResponse:
        self.payload = payload
        return SignupResponse(
            id=uuid4(),
            email=payload.email,
            name=payload.name,
            phone=payload.phone,
            email_verified_at=None,
            created_at=datetime(2026, 6, 7, tzinfo=UTC),
            updated_at=datetime(2026, 6, 7, tzinfo=UTC),
        )


class FakeSession:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False
        self.refreshed_user_id: UUID | None = None

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True

    async def refresh(self, user: SimpleNamespace) -> None:
        self.refreshed_user_id = user.id


class FakeUserRepository:
    def __init__(
        self,
        existing_user: SimpleNamespace | None = None,
        create_error: Exception | None = None,
    ) -> None:
        self.existing_user = existing_user
        self.create_error = create_error
        self.created_user: SimpleNamespace | None = None

    async def get_by_email(self, email: str) -> SimpleNamespace | None:
        return self.existing_user

    async def create(
        self,
        *,
        email: str,
        password_hash: str,
        name: str,
        phone: str | None,
    ) -> SimpleNamespace:
        if self.create_error is not None:
            raise self.create_error
        self.created_user = SimpleNamespace(
            id=uuid4(),
            email=email,
            password_hash=password_hash,
            name=name,
            phone=phone,
            email_verified_at=None,
            created_at=datetime(2026, 6, 7, tzinfo=UTC),
            updated_at=datetime(2026, 6, 7, tzinfo=UTC),
        )
        return self.created_user


class FakePasswordService:
    def __init__(self) -> None:
        self.raw_password: str | None = None

    def hash_password(self, password: str) -> str:
        self.raw_password = password
        return "argon2id-hash"


def test_signup_returns_created_user_without_sensitive_fields() -> None:
    fake_auth_service = FakeAuthService()
    app.dependency_overrides[get_auth_service] = lambda: fake_auth_service

    try:
        client = TestClient(app)
        response = client.post(
            "/api/v1/auth/signup",
            json={
                "email": "User@Example.com",
                "password": "safe-password",
                "name": "해조",
                "phone": "010-1234-5678",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    body = response.json()
    assert body["email"] == "user@example.com"
    assert body["name"] == "해조"
    assert body["phone"] == "010-1234-5678"
    assert body["email_verified_at"] is None
    assert "password" not in body
    assert "password_hash" not in body
    assert fake_auth_service.payload is not None
    assert fake_auth_service.payload.email == "user@example.com"


def test_auth_service_creates_user_with_hashed_password() -> None:
    async def run_signup() -> None:
        session = FakeSession()
        user_repository = FakeUserRepository()
        password_service = FakePasswordService()
        auth_service = AuthService(
            session=session,
            user_repository=user_repository,
            password_service=password_service,
        )
        payload = SignupRequest(
            email="user@example.com",
            password="safe-password",
            name="해조",
            phone=None,
        )

        response = await auth_service.signup(payload)

        assert user_repository.created_user is not None
        assert user_repository.created_user.password_hash == "argon2id-hash"
        assert user_repository.created_user.email_verified_at is None
        assert password_service.raw_password == "safe-password"
        assert session.committed is True
        assert session.rolled_back is False
        assert session.refreshed_user_id == response.id
        assert response.email == "user@example.com"

    asyncio.run(run_signup())


def test_password_service_hashes_password_with_argon2id() -> None:
    password_service = PasswordService()

    password_hash = password_service.hash_password("safe-password")

    assert password_hash.startswith("$argon2id$")
    assert PasswordHasher().verify(password_hash, "safe-password") is True


def test_auth_service_rejects_duplicate_email() -> None:
    async def run_signup() -> None:
        session = FakeSession()
        auth_service = AuthService(
            session=session,
            user_repository=FakeUserRepository(existing_user=SimpleNamespace(id=uuid4())),
            password_service=FakePasswordService(),
        )
        payload = SignupRequest(
            email="user@example.com",
            password="safe-password",
            name="해조",
            phone=None,
        )

        with pytest.raises(AppException) as exc_info:
            await auth_service.signup(payload)

        assert exc_info.value.code == error_codes.EMAIL_ALREADY_EXISTS
        assert exc_info.value.status_code == 409
        assert session.committed is False

    asyncio.run(run_signup())


def test_auth_service_converts_unique_constraint_error_to_duplicate_email_error() -> None:
    async def run_signup() -> None:
        session = FakeSession()
        auth_service = AuthService(
            session=session,
            user_repository=FakeUserRepository(
                create_error=IntegrityError("insert users", {}, Exception("duplicate email"))
            ),
            password_service=FakePasswordService(),
        )
        payload = SignupRequest(
            email="user@example.com",
            password="safe-password",
            name="해조",
            phone=None,
        )

        with pytest.raises(AppException) as exc_info:
            await auth_service.signup(payload)

        assert exc_info.value.code == error_codes.EMAIL_ALREADY_EXISTS
        assert exc_info.value.status_code == 409
        assert session.rolled_back is True

    asyncio.run(run_signup())
