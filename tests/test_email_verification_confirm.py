import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_email_verification_service
from app.core import error_codes
from app.core.exceptions import AppException
from app.main import app
from app.services.email_verification_service import (
    EmailVerificationConfirmResult,
    EmailVerificationService,
)


class FakeSession:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


class FakeUserRepository:
    def __init__(self, user: SimpleNamespace | None) -> None:
        self.user = user
        self.locked_user_id: UUID | None = None
        self.verified_user_id: UUID | None = None
        self.verified_at: datetime | None = None

    async def get_by_id_for_update(self, user_id: UUID) -> SimpleNamespace | None:
        self.locked_user_id = user_id
        return self.user

    async def mark_email_verified(
        self,
        user: SimpleNamespace,
        *,
        verified_at: datetime,
    ) -> SimpleNamespace:
        self.verified_user_id = user.id
        self.verified_at = verified_at
        user.email_verified_at = verified_at
        return user


class FakeEmailVerificationTokenRepository:
    def __init__(self, token_row: SimpleNamespace | None) -> None:
        self.token_row = token_row
        self.requested_token_hash: str | None = None
        self.used_token_id: UUID | None = None
        self.used_at: datetime | None = None

    async def get_by_token_hash_for_update(
        self,
        token_hash: str,
    ) -> SimpleNamespace | None:
        self.requested_token_hash = token_hash
        return self.token_row

    async def mark_used(
        self,
        email_verification_token: SimpleNamespace,
        *,
        used_at: datetime,
    ) -> SimpleNamespace:
        self.used_token_id = email_verification_token.id
        self.used_at = used_at
        email_verification_token.used_at = used_at
        return email_verification_token


class FakeEmailVerificationService:
    def __init__(self) -> None:
        self.token: str | None = None

    async def confirm_email_verification(self, *, token: str) -> EmailVerificationConfirmResult:
        self.token = token
        return EmailVerificationConfirmResult(
            email_verified_at=datetime(2026, 6, 8, 12, 30, tzinfo=UTC),
        )


def make_user(*, email_verified_at: datetime | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        email_verified_at=email_verified_at,
        deleted_at=None,
    )


def make_token_row(
    *,
    user_id: UUID,
    expires_at: datetime | None = None,
    used_at: datetime | None = None,
    revoked_at: datetime | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        user_id=user_id,
        expires_at=expires_at or datetime.now(UTC) + timedelta(minutes=30),
        used_at=used_at,
        revoked_at=revoked_at,
    )


def test_confirm_email_verification_returns_verified_at() -> None:
    fake_service = FakeEmailVerificationService()
    app.dependency_overrides[get_email_verification_service] = lambda: fake_service

    try:
        client = TestClient(app)
        response = client.post(
            "/api/v1/auth/email-verification/confirm",
            json={"token": " dev-token "},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"email_verified_at": "2026-06-08T12:30:00Z"}
    assert fake_service.token == "dev-token"


def test_email_verification_service_confirms_valid_token() -> None:
    async def run_confirm() -> None:
        session = FakeSession()
        user = make_user()
        token_row = make_token_row(user_id=user.id)
        user_repository = FakeUserRepository(user)
        token_repository = FakeEmailVerificationTokenRepository(token_row)
        service = EmailVerificationService(
            session=session,
            user_repository=user_repository,
            email_verification_token_repository=token_repository,
        )

        result = await service.confirm_email_verification(token="dev-token")

        assert token_repository.requested_token_hash == service.hash_token("dev-token")
        assert user_repository.locked_user_id == user.id
        assert user_repository.verified_user_id == user.id
        assert user_repository.verified_at == result.email_verified_at
        assert token_repository.used_token_id == token_row.id
        assert token_repository.used_at is not None
        assert session.committed is True
        assert session.rolled_back is False

    asyncio.run(run_confirm())


def test_email_verification_service_marks_token_used_for_already_verified_user() -> None:
    async def run_confirm() -> None:
        session = FakeSession()
        verified_at = datetime(2026, 6, 8, 12, 0, tzinfo=UTC)
        user = make_user(email_verified_at=verified_at)
        token_row = make_token_row(user_id=user.id)
        user_repository = FakeUserRepository(user)
        token_repository = FakeEmailVerificationTokenRepository(token_row)
        service = EmailVerificationService(
            session=session,
            user_repository=user_repository,
            email_verification_token_repository=token_repository,
        )

        result = await service.confirm_email_verification(token="dev-token")

        assert result.email_verified_at == verified_at
        assert user_repository.verified_user_id is None
        assert token_repository.used_token_id == token_row.id
        assert session.committed is True

    asyncio.run(run_confirm())


@pytest.mark.parametrize(
    "token_row",
    [
        None,
        make_token_row(user_id=uuid4(), expires_at=datetime.now(UTC) - timedelta(minutes=1)),
        make_token_row(user_id=uuid4(), used_at=datetime.now(UTC)),
        make_token_row(user_id=uuid4(), revoked_at=datetime.now(UTC)),
    ],
)
def test_email_verification_service_rejects_invalid_token_states(
    token_row: SimpleNamespace | None,
) -> None:
    async def run_confirm() -> None:
        session = FakeSession()
        service = EmailVerificationService(
            session=session,
            user_repository=FakeUserRepository(make_user()),
            email_verification_token_repository=FakeEmailVerificationTokenRepository(token_row),
        )

        with pytest.raises(AppException) as exc_info:
            await service.confirm_email_verification(token="dev-token")

        assert exc_info.value.code == error_codes.INVALID_EMAIL_VERIFICATION_TOKEN
        assert exc_info.value.status_code == 400
        assert session.committed is False

    asyncio.run(run_confirm())


def test_email_verification_service_rejects_missing_user() -> None:
    async def run_confirm() -> None:
        session = FakeSession()
        token_row = make_token_row(user_id=uuid4())
        service = EmailVerificationService(
            session=session,
            user_repository=FakeUserRepository(None),
            email_verification_token_repository=FakeEmailVerificationTokenRepository(token_row),
        )

        with pytest.raises(AppException) as exc_info:
            await service.confirm_email_verification(token="dev-token")

        assert exc_info.value.code == error_codes.INVALID_EMAIL_VERIFICATION_TOKEN
        assert exc_info.value.status_code == 400
        assert session.committed is False

    asyncio.run(run_confirm())
