import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.deps import CurrentUser, get_email_verification_service, require_authenticated
from app.core import error_codes
from app.core.exceptions import AppException
from app.integrations.email.email_service import EmailMessage
from app.main import app
from app.services.email_verification_service import (
    EmailVerificationRequestResult,
    EmailVerificationService,
)


class FakeSession:
    def __init__(self) -> None:
        self.commit_count = 0
        self.rolled_back = False

    @property
    def committed(self) -> bool:
        return self.commit_count > 0

    async def commit(self) -> None:
        self.commit_count += 1

    async def rollback(self) -> None:
        self.rolled_back = True


class FakeUserRepository:
    def __init__(self, user: SimpleNamespace | None) -> None:
        self.user = user
        self.requested_user_id: UUID | None = None
        self.locked_user_id: UUID | None = None

    async def get_by_id(self, user_id: UUID) -> SimpleNamespace | None:
        self.requested_user_id = user_id
        return self.user

    async def get_by_id_for_update(self, user_id: UUID) -> SimpleNamespace | None:
        self.locked_user_id = user_id
        return self.user


class FakeEmailVerificationTokenRepository:
    def __init__(self) -> None:
        self.revoked_user_id: UUID | None = None
        self.revoked_at: datetime | None = None
        self.created_user_id: UUID | None = None
        self.created_token: SimpleNamespace | None = None
        self.token_hash: str | None = None
        self.expires_at: datetime | None = None
        self.revoked_token_id: UUID | None = None
        self.failed_delivery_revoked_at: datetime | None = None

    async def revoke_active_tokens(self, *, user_id: UUID, revoked_at: datetime) -> None:
        self.revoked_user_id = user_id
        self.revoked_at = revoked_at

    async def create(
        self,
        *,
        user_id: UUID,
        token_hash: str,
        expires_at: datetime,
    ) -> SimpleNamespace:
        self.created_user_id = user_id
        self.token_hash = token_hash
        self.expires_at = expires_at
        self.created_token = SimpleNamespace(id=uuid4(), revoked_at=None)
        return self.created_token

    async def mark_revoked(
        self,
        email_verification_token: SimpleNamespace,
        *,
        revoked_at: datetime,
    ) -> SimpleNamespace:
        self.revoked_token_id = email_verification_token.id
        self.failed_delivery_revoked_at = revoked_at
        email_verification_token.revoked_at = revoked_at
        return email_verification_token


class FakeEmailService:
    def __init__(self, *, send_error: Exception | None = None) -> None:
        self.send_error = send_error
        self.sent_message: EmailMessage | None = None

    async def send_email(self, message: EmailMessage) -> None:
        self.sent_message = message
        if self.send_error is not None:
            raise self.send_error


class FakeEmailVerificationService:
    def __init__(self) -> None:
        self.user_id: UUID | None = None

    async def request_verification_email(self, *, user_id: UUID) -> EmailVerificationRequestResult:
        self.user_id = user_id
        return EmailVerificationRequestResult(
            expires_at=datetime(2026, 6, 8, 12, 30, tzinfo=UTC),
            verification_url="http://localhost:3000/email-verification?token=dev-token",
        )


def make_user(*, email_verified_at: datetime | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        email="user@example.com",
        email_verified_at=email_verified_at,
        deleted_at=None,
    )


def test_request_email_verification_returns_dev_verification_url() -> None:
    user_id = uuid4()
    fake_service = FakeEmailVerificationService()

    app.dependency_overrides[require_authenticated] = lambda: CurrentUser(
        id=user_id,
        email_verified_at=None,
    )
    app.dependency_overrides[get_email_verification_service] = lambda: fake_service

    try:
        client = TestClient(app)
        response = client.post("/api/v1/auth/email-verification/request")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "expires_at": "2026-06-08T12:30:00Z",
        "verification_url": "http://localhost:3000/email-verification?token=dev-token",
    }
    assert fake_service.user_id == user_id


def test_email_verification_service_creates_hashed_token_and_revokes_existing_tokens() -> None:
    async def run_request() -> None:
        session = FakeSession()
        user = make_user()
        user_repository = FakeUserRepository(user)
        token_repository = FakeEmailVerificationTokenRepository()
        email_service = FakeEmailService()
        service = EmailVerificationService(
            session=session,
            user_repository=user_repository,
            email_verification_token_repository=token_repository,
            email_service=email_service,
        )

        result = await service.request_verification_email(user_id=user.id)

        assert user_repository.locked_user_id == user.id
        assert user_repository.requested_user_id is None
        assert token_repository.revoked_user_id == user.id
        assert token_repository.revoked_at is not None
        assert token_repository.created_user_id == user.id
        assert token_repository.expires_at == result.expires_at
        assert token_repository.token_hash is not None
        assert len(token_repository.token_hash) == 64
        assert result.verification_url is not None
        token = parse_qs(urlparse(result.verification_url).query)["token"][0]
        assert token_repository.token_hash == service.hash_token(token)
        assert token_repository.token_hash != token
        assert email_service.sent_message is not None
        assert email_service.sent_message.to_email == "user@example.com"
        assert token in email_service.sent_message.text_body
        assert session.committed is True
        assert session.commit_count == 1
        assert session.rolled_back is False

    asyncio.run(run_request())


def test_email_verification_service_rejects_already_verified_user() -> None:
    async def run_request() -> None:
        session = FakeSession()
        user = make_user(email_verified_at=datetime(2026, 6, 8, tzinfo=UTC))
        service = EmailVerificationService(
            session=session,
            user_repository=FakeUserRepository(user),
            email_verification_token_repository=FakeEmailVerificationTokenRepository(),
            email_service=FakeEmailService(),
        )

        with pytest.raises(AppException) as exc_info:
            await service.request_verification_email(user_id=user.id)

        assert exc_info.value.code == error_codes.EMAIL_ALREADY_VERIFIED
        assert exc_info.value.status_code == 409
        assert session.committed is False

    asyncio.run(run_request())


def test_email_verification_service_rejects_missing_user() -> None:
    async def run_request() -> None:
        session = FakeSession()
        service = EmailVerificationService(
            session=session,
            user_repository=FakeUserRepository(None),
            email_verification_token_repository=FakeEmailVerificationTokenRepository(),
            email_service=FakeEmailService(),
        )

        with pytest.raises(AppException) as exc_info:
            await service.request_verification_email(user_id=uuid4())

        assert exc_info.value.code == error_codes.UNAUTHORIZED
        assert exc_info.value.status_code == 401
        assert session.committed is False

    asyncio.run(run_request())


def test_email_verification_service_revokes_token_when_email_delivery_fails() -> None:
    async def run_request() -> None:
        session = FakeSession()
        user = make_user()
        token_repository = FakeEmailVerificationTokenRepository()
        service = EmailVerificationService(
            session=session,
            user_repository=FakeUserRepository(user),
            email_verification_token_repository=token_repository,
            email_service=FakeEmailService(send_error=RuntimeError("smtp failed")),
        )

        with pytest.raises(AppException) as exc_info:
            await service.request_verification_email(user_id=user.id)

        assert exc_info.value.code == error_codes.EXTERNAL_SERVICE_ERROR
        assert exc_info.value.status_code == 502
        assert token_repository.created_token is not None
        assert token_repository.revoked_token_id == token_repository.created_token.id
        assert token_repository.failed_delivery_revoked_at is not None
        assert session.commit_count == 2
        assert session.rolled_back is False

    asyncio.run(run_request())
