import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import jwt
import pytest
from fastapi.security import HTTPAuthorizationCredentials

from app.api.deps import CurrentUser, require_authenticated, require_email_verified
from app.core import error_codes
from app.core.config import settings
from app.core.exceptions import AppException
from app.services.token_service import TokenService


class FakeResult:
    def __init__(self, user: SimpleNamespace | None) -> None:
        self.user = user

    def scalar_one_or_none(self) -> SimpleNamespace | None:
        return self.user


class FakeSession:
    def __init__(self, user: SimpleNamespace | None) -> None:
        self.user = user

    async def execute(self, _) -> FakeResult:
        return FakeResult(self.user)


def make_credentials(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


def make_user(*, email_verified_at: datetime | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        email_verified_at=email_verified_at,
        deleted_at=None,
    )


def test_require_authenticated_returns_current_user_from_access_token() -> None:
    async def run_auth() -> None:
        user = make_user(email_verified_at=datetime.now(UTC))
        token = TokenService().create_access_token(user_id=user.id)

        current_user = await require_authenticated(make_credentials(token), FakeSession(user))

        assert current_user.id == user.id
        assert current_user.email_verified_at == user.email_verified_at

    asyncio.run(run_auth())


def test_require_authenticated_rejects_missing_bearer_token() -> None:
    async def run_auth() -> None:
        with pytest.raises(AppException) as exc_info:
            await require_authenticated(None, FakeSession(None))

        assert exc_info.value.code == error_codes.UNAUTHORIZED
        assert exc_info.value.status_code == 401

    asyncio.run(run_auth())


def test_require_authenticated_rejects_expired_access_token() -> None:
    async def run_auth() -> None:
        user = make_user()
        now = datetime.now(UTC)
        token = jwt.encode(
            {
                "sub": str(user.id),
                "iat": int((now - timedelta(minutes=10)).timestamp()),
                "exp": int((now - timedelta(minutes=1)).timestamp()),
                "type": "access",
            },
            settings.jwt_secret,
            algorithm=settings.jwt_algorithm,
        )

        with pytest.raises(AppException) as exc_info:
            await require_authenticated(make_credentials(token), FakeSession(user))

        assert exc_info.value.code == error_codes.TOKEN_EXPIRED
        assert exc_info.value.status_code == 401

    asyncio.run(run_auth())


def test_require_authenticated_rejects_access_token_without_expiration() -> None:
    async def run_auth() -> None:
        user = make_user()
        now = datetime.now(UTC)
        token = jwt.encode(
            {
                "sub": str(user.id),
                "iat": int(now.timestamp()),
                "type": "access",
            },
            settings.jwt_secret,
            algorithm=settings.jwt_algorithm,
        )

        with pytest.raises(AppException) as exc_info:
            await require_authenticated(make_credentials(token), FakeSession(user))

        assert exc_info.value.code == error_codes.INVALID_TOKEN
        assert exc_info.value.status_code == 401

    asyncio.run(run_auth())


def test_require_authenticated_rejects_refresh_token_type() -> None:
    async def run_auth() -> None:
        user = make_user()
        now = datetime.now(UTC)
        token = jwt.encode(
            {
                "sub": str(user.id),
                "iat": int(now.timestamp()),
                "exp": int((now + timedelta(minutes=30)).timestamp()),
                "type": "refresh",
            },
            settings.jwt_secret,
            algorithm=settings.jwt_algorithm,
        )

        with pytest.raises(AppException) as exc_info:
            await require_authenticated(make_credentials(token), FakeSession(user))

        assert exc_info.value.code == error_codes.INVALID_TOKEN
        assert exc_info.value.status_code == 401

    asyncio.run(run_auth())


def test_require_authenticated_rejects_missing_user() -> None:
    async def run_auth() -> None:
        token = TokenService().create_access_token(user_id=uuid4())

        with pytest.raises(AppException) as exc_info:
            await require_authenticated(make_credentials(token), FakeSession(None))

        assert exc_info.value.code == error_codes.UNAUTHORIZED
        assert exc_info.value.status_code == 401

    asyncio.run(run_auth())


def test_require_email_verified_rejects_unverified_user() -> None:
    async def run_auth() -> None:
        current_user = CurrentUser(id=uuid4(), email_verified_at=None)

        with pytest.raises(AppException) as exc_info:
            await require_email_verified(current_user)

        assert exc_info.value.code == error_codes.EMAIL_NOT_VERIFIED
        assert exc_info.value.status_code == 403

    asyncio.run(run_auth())


def test_require_email_verified_returns_verified_user() -> None:
    async def run_auth() -> None:
        current_user = CurrentUser(id=uuid4(), email_verified_at=datetime.now(UTC))

        verified_user = await require_email_verified(current_user)

        assert verified_user == current_user

    asyncio.run(run_auth())
