import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.api.deps import get_auth_service
from app.api.v1 import auth as auth_router
from app.core import error_codes
from app.core.exceptions import AppException
from app.main import app
from app.schemas.auth import LoginRequest, LoginResponse, SignupRequest, SignupResponse
from app.services.auth_service import AuthService
from app.services.password_service import PasswordService


class FakeAuthService:
    def __init__(self) -> None:
        self.payload: SignupRequest | None = None
        self.login_payload: LoginRequest | None = None
        self.refresh_token: str | None = None

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

    async def login(self, payload: LoginRequest) -> tuple[LoginResponse, str]:
        self.login_payload = payload
        return LoginResponse(access_token="access-token"), "refresh-token"

    async def refresh(self, refresh_token: str) -> tuple[LoginResponse, str]:
        return LoginResponse(access_token=f"access-token-for-{refresh_token}"), "new-refresh-token"

    async def logout(self, refresh_token: str) -> None:
        self.refresh_token = refresh_token

    def raise_invalid_refresh_token(self) -> None:
        raise AppException(
            code=error_codes.INVALID_REFRESH_TOKEN,
            message="Invalid refresh token.",
            status_code=401,
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
        self.locked_user_id: UUID | None = None

    async def get_by_email(self, email: str) -> SimpleNamespace | None:
        return self.existing_user

    async def get_by_id_for_update(self, user_id: UUID) -> SimpleNamespace | None:
        self.locked_user_id = user_id
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


DEFAULT_FREE_PLAN = object()


class FakePlanRepository:
    def __init__(self, free_plan: SimpleNamespace | None | object = DEFAULT_FREE_PLAN) -> None:
        self.free_plan = (
            SimpleNamespace(id=uuid4(), code="FREE")
            if free_plan is DEFAULT_FREE_PLAN
            else free_plan
        )
        self.free_plan_requested = False

    async def get_free_plan(self) -> SimpleNamespace | None:
        self.free_plan_requested = True
        return self.free_plan


class FakeSubscriptionRepository:
    def __init__(self) -> None:
        self.created_user_id: UUID | None = None
        self.created_plan_id: UUID | None = None

    async def create_free_subscription(
        self,
        *,
        user_id: UUID,
        plan_id: UUID,
    ) -> SimpleNamespace:
        self.created_user_id = user_id
        self.created_plan_id = plan_id
        return SimpleNamespace(id=uuid4(), user_id=user_id, plan_id=plan_id)


class FakeRefreshTokenRepository:
    def __init__(self, stored_refresh_token: SimpleNamespace | None = None) -> None:
        self.stored_refresh_token = stored_refresh_token
        self.user_id: UUID | None = None
        self.token_hash: str | None = None
        self.expires_at: datetime | None = None
        self.requested_token_hash: str | None = None
        self.revoked_token_id: UUID | None = None
        self.revoked_at: datetime | None = None

    async def get_by_token_hash_for_update(self, token_hash: str) -> SimpleNamespace | None:
        self.requested_token_hash = token_hash
        return self.stored_refresh_token

    async def revoke(
        self,
        refresh_token: SimpleNamespace,
        *,
        revoked_at: datetime,
    ) -> SimpleNamespace:
        self.revoked_token_id = refresh_token.id
        self.revoked_at = revoked_at
        refresh_token.revoked_at = revoked_at
        return refresh_token

    async def create(
        self,
        *,
        user_id: UUID,
        token_hash: str,
        expires_at: datetime,
    ) -> SimpleNamespace:
        self.user_id = user_id
        self.token_hash = token_hash
        self.expires_at = expires_at
        return SimpleNamespace(id=uuid4())


class FakePasswordService:
    def __init__(self) -> None:
        self.raw_password: str | None = None
        self.verified_password: str | None = None
        self.verified_hash: str | None = None
        self.verify_result = True

    def hash_password(self, password: str) -> str:
        self.raw_password = password
        return "argon2id-hash"

    def verify_password(self, password: str, password_hash: str) -> bool:
        self.verified_password = password
        self.verified_hash = password_hash
        return self.verify_result


class FakeTokenService:
    def create_access_token(self, *, user_id: UUID) -> str:
        return f"access-token-for-{user_id}"

    def create_refresh_token(self) -> str:
        return "refresh-token"

    def hash_refresh_token(self, refresh_token: str) -> str:
        return f"hashed-{refresh_token}"

    def get_refresh_token_expires_at(self) -> datetime:
        return datetime(2099, 1, 1, tzinfo=UTC)


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


def test_signup_rejects_non_string_trimmed_fields_with_validation_error() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/v1/auth/signup",
        json={
            "email": "user@example.com",
            "password": "safe-password",
            "name": None,
            "phone": 1234,
        },
    )

    assert response.status_code == 422


def test_login_returns_access_token_and_sets_refresh_token_cookie() -> None:
    fake_auth_service = FakeAuthService()
    app.dependency_overrides[get_auth_service] = lambda: fake_auth_service

    try:
        client = TestClient(app)
        response = client.post(
            "/api/v1/auth/login",
            json={
                "email": "User@Example.com",
                "password": "safe-password",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"access_token": "access-token", "token_type": "bearer"}
    assert response.cookies.get("refresh_token") == "refresh-token"
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "Path=/api/v1/auth" in response.headers["set-cookie"]
    assert fake_auth_service.login_payload is not None
    assert fake_auth_service.login_payload.email == "user@example.com"


def test_refresh_rotates_refresh_token_cookie() -> None:
    fake_auth_service = FakeAuthService()
    app.dependency_overrides[get_auth_service] = lambda: fake_auth_service

    try:
        client = TestClient(app)
        client.cookies.set("refresh_token", "refresh-token")
        response = client.post("/api/v1/auth/refresh")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "access_token": "access-token-for-refresh-token",
        "token_type": "bearer",
    }
    assert response.cookies.get("refresh_token") == "new-refresh-token"
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "Path=/api/v1/auth" in response.headers["set-cookie"]


def test_refresh_rejects_missing_refresh_token_cookie() -> None:
    fake_auth_service = FakeAuthService()
    app.dependency_overrides[get_auth_service] = lambda: fake_auth_service

    try:
        client = TestClient(app)
        response = client.post("/api/v1/auth/refresh")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401
    assert response.json()["error"]["code"] == error_codes.INVALID_REFRESH_TOKEN


def test_logout_revokes_refresh_token_cookie() -> None:
    fake_auth_service = FakeAuthService()
    app.dependency_overrides[get_auth_service] = lambda: fake_auth_service

    try:
        client = TestClient(app)
        client.cookies.set("refresh_token", "refresh-token")
        response = client.post("/api/v1/auth/logout")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 204
    assert fake_auth_service.refresh_token == "refresh-token"
    assert "refresh_token=" in response.headers["set-cookie"]
    assert "Max-Age=0" in response.headers["set-cookie"]
    assert "Path=/api/v1/auth" in response.headers["set-cookie"]


def test_logout_clears_cookie_without_refresh_token_cookie() -> None:
    fake_auth_service = FakeAuthService()
    app.dependency_overrides[get_auth_service] = lambda: fake_auth_service

    try:
        client = TestClient(app)
        response = client.post("/api/v1/auth/logout")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 204
    assert fake_auth_service.refresh_token is None
    assert "refresh_token=" in response.headers["set-cookie"]
    assert "Max-Age=0" in response.headers["set-cookie"]


def test_refresh_cookie_path_uses_configured_api_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(auth_router.settings, "api_v1_prefix", "/custom-api/")

    assert auth_router.get_refresh_token_cookie_path() == "/custom-api/auth"


def test_auth_service_creates_user_with_hashed_password() -> None:
    async def run_signup() -> None:
        session = FakeSession()
        user_repository = FakeUserRepository()
        plan_repository = FakePlanRepository()
        subscription_repository = FakeSubscriptionRepository()
        password_service = FakePasswordService()
        auth_service = AuthService(
            session=session,
            user_repository=user_repository,
            plan_repository=plan_repository,
            subscription_repository=subscription_repository,
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
        assert plan_repository.free_plan_requested is True
        assert subscription_repository.created_user_id == user_repository.created_user.id
        assert subscription_repository.created_plan_id == plan_repository.free_plan.id
        assert password_service.raw_password == "safe-password"
        assert session.committed is True
        assert session.rolled_back is False
        assert session.refreshed_user_id == response.id
        assert response.email == "user@example.com"

    asyncio.run(run_signup())


def test_auth_service_rolls_back_when_free_plan_is_missing() -> None:
    async def run_signup() -> None:
        session = FakeSession()
        user_repository = FakeUserRepository()
        subscription_repository = FakeSubscriptionRepository()
        auth_service = AuthService(
            session=session,
            user_repository=user_repository,
            plan_repository=FakePlanRepository(free_plan=None),
            subscription_repository=subscription_repository,
            password_service=FakePasswordService(),
        )
        payload = SignupRequest(
            email="user@example.com",
            password="safe-password",
            name="?댁“",
            phone=None,
        )

        with pytest.raises(AppException) as exc_info:
            await auth_service.signup(payload)

        assert exc_info.value.code == error_codes.PLAN_NOT_FOUND
        assert exc_info.value.status_code == 500
        assert user_repository.created_user is not None
        assert subscription_repository.created_user_id is None
        assert session.committed is False
        assert session.rolled_back is True

    asyncio.run(run_signup())


def test_auth_service_login_creates_tokens_and_stores_refresh_token_hash() -> None:
    async def run_login() -> None:
        user_id = uuid4()
        session = FakeSession()
        user_repository = FakeUserRepository(
            existing_user=SimpleNamespace(
                id=user_id,
                email="user@example.com",
                password_hash="argon2id-hash",
            )
        )
        refresh_token_repository = FakeRefreshTokenRepository()
        password_service = FakePasswordService()
        auth_service = AuthService(
            session=session,
            user_repository=user_repository,
            refresh_token_repository=refresh_token_repository,
            password_service=password_service,
            token_service=FakeTokenService(),
        )
        payload = LoginRequest(email="user@example.com", password="safe-password")

        login_response, refresh_token = await auth_service.login(payload)

        assert login_response.access_token == f"access-token-for-{user_id}"
        assert refresh_token == "refresh-token"
        assert refresh_token_repository.user_id == user_id
        assert refresh_token_repository.token_hash == "hashed-refresh-token"
        assert refresh_token_repository.expires_at == datetime(2099, 1, 1, tzinfo=UTC)
        assert password_service.verified_password == "safe-password"
        assert password_service.verified_hash == "argon2id-hash"
        assert session.committed is True

    asyncio.run(run_login())


def test_auth_service_refresh_rotates_refresh_token() -> None:
    async def run_refresh() -> None:
        user_id = uuid4()
        refresh_token_row = SimpleNamespace(
            id=uuid4(),
            user_id=user_id,
            expires_at=datetime(2099, 1, 1, tzinfo=UTC),
            revoked_at=None,
        )
        session = FakeSession()
        user_repository = FakeUserRepository(
            existing_user=SimpleNamespace(
                id=user_id,
                deleted_at=None,
            )
        )
        refresh_token_repository = FakeRefreshTokenRepository(
            stored_refresh_token=refresh_token_row,
        )
        auth_service = AuthService(
            session=session,
            user_repository=user_repository,
            refresh_token_repository=refresh_token_repository,
            token_service=FakeTokenService(),
        )

        refresh_response, new_refresh_token = await auth_service.refresh("refresh-token")

        assert refresh_response.access_token == f"access-token-for-{user_id}"
        assert new_refresh_token == "refresh-token"
        assert refresh_token_repository.requested_token_hash == "hashed-refresh-token"
        assert refresh_token_repository.revoked_token_id == refresh_token_row.id
        assert refresh_token_repository.revoked_at is not None
        assert refresh_token_repository.user_id == user_id
        assert refresh_token_repository.token_hash == "hashed-refresh-token"
        assert refresh_token_repository.expires_at == datetime(2099, 1, 1, tzinfo=UTC)
        assert user_repository.locked_user_id == user_id
        assert session.committed is True
        assert session.rolled_back is False

    asyncio.run(run_refresh())


@pytest.mark.parametrize(
    "stored_refresh_token",
    [
        None,
        SimpleNamespace(
            id=uuid4(),
            user_id=uuid4(),
            expires_at=datetime(2099, 1, 1, tzinfo=UTC),
            revoked_at=datetime(2026, 6, 8, tzinfo=UTC),
        ),
        SimpleNamespace(
            id=uuid4(),
            user_id=uuid4(),
            expires_at=datetime(2026, 6, 1, tzinfo=UTC),
            revoked_at=None,
        ),
    ],
)
def test_auth_service_refresh_rejects_invalid_refresh_token(
    stored_refresh_token: SimpleNamespace | None,
) -> None:
    async def run_refresh() -> None:
        session = FakeSession()
        auth_service = AuthService(
            session=session,
            user_repository=FakeUserRepository(
                existing_user=SimpleNamespace(id=uuid4(), deleted_at=None)
            ),
            refresh_token_repository=FakeRefreshTokenRepository(
                stored_refresh_token=stored_refresh_token,
            ),
            token_service=FakeTokenService(),
        )

        with pytest.raises(AppException) as exc_info:
            await auth_service.refresh("refresh-token")

        assert exc_info.value.code == error_codes.INVALID_REFRESH_TOKEN
        assert exc_info.value.status_code == 401
        assert session.committed is False

    asyncio.run(run_refresh())


def test_auth_service_refresh_rejects_missing_user() -> None:
    async def run_refresh() -> None:
        session = FakeSession()
        auth_service = AuthService(
            session=session,
            user_repository=FakeUserRepository(existing_user=None),
            refresh_token_repository=FakeRefreshTokenRepository(
                stored_refresh_token=SimpleNamespace(
                    id=uuid4(),
                    user_id=uuid4(),
                    expires_at=datetime(2099, 1, 1, tzinfo=UTC),
                    revoked_at=None,
                ),
            ),
            token_service=FakeTokenService(),
        )

        with pytest.raises(AppException) as exc_info:
            await auth_service.refresh("refresh-token")

        assert exc_info.value.code == error_codes.INVALID_REFRESH_TOKEN
        assert exc_info.value.status_code == 401
        assert session.committed is False

    asyncio.run(run_refresh())


def test_auth_service_logout_revokes_refresh_token() -> None:
    async def run_logout() -> None:
        refresh_token_row = SimpleNamespace(
            id=uuid4(),
            user_id=uuid4(),
            expires_at=datetime(2099, 1, 1, tzinfo=UTC),
            revoked_at=None,
        )
        session = FakeSession()
        refresh_token_repository = FakeRefreshTokenRepository(
            stored_refresh_token=refresh_token_row,
        )
        auth_service = AuthService(
            session=session,
            refresh_token_repository=refresh_token_repository,
            token_service=FakeTokenService(),
        )

        await auth_service.logout("refresh-token")

        assert refresh_token_repository.requested_token_hash == "hashed-refresh-token"
        assert refresh_token_repository.revoked_token_id == refresh_token_row.id
        assert refresh_token_repository.revoked_at is not None
        assert refresh_token_row.revoked_at is not None
        assert session.committed is True
        assert session.rolled_back is False

    asyncio.run(run_logout())


@pytest.mark.parametrize(
    "stored_refresh_token",
    [
        None,
        SimpleNamespace(
            id=uuid4(),
            user_id=uuid4(),
            expires_at=datetime(2099, 1, 1, tzinfo=UTC),
            revoked_at=datetime(2026, 6, 8, tzinfo=UTC),
        ),
    ],
)
def test_auth_service_logout_ignores_missing_or_revoked_refresh_token(
    stored_refresh_token: SimpleNamespace | None,
) -> None:
    async def run_logout() -> None:
        session = FakeSession()
        refresh_token_repository = FakeRefreshTokenRepository(
            stored_refresh_token=stored_refresh_token,
        )
        auth_service = AuthService(
            session=session,
            refresh_token_repository=refresh_token_repository,
            token_service=FakeTokenService(),
        )

        await auth_service.logout("refresh-token")

        assert refresh_token_repository.requested_token_hash == "hashed-refresh-token"
        assert refresh_token_repository.revoked_token_id is None
        assert session.committed is False
        assert session.rolled_back is False

    asyncio.run(run_logout())


def test_auth_service_login_rejects_invalid_credentials() -> None:
    async def run_login() -> None:
        session = FakeSession()
        password_service = FakePasswordService()
        password_service.verify_result = False
        auth_service = AuthService(
            session=session,
            user_repository=FakeUserRepository(
                existing_user=SimpleNamespace(
                    id=uuid4(),
                    email="user@example.com",
                    password_hash="argon2id-hash",
                )
            ),
            refresh_token_repository=FakeRefreshTokenRepository(),
            password_service=password_service,
            token_service=FakeTokenService(),
        )

        with pytest.raises(AppException) as exc_info:
            await auth_service.login(LoginRequest(email="user@example.com", password="wrong"))

        assert exc_info.value.code == error_codes.INVALID_CREDENTIALS
        assert exc_info.value.status_code == 401
        assert session.committed is False

    asyncio.run(run_login())


def test_auth_service_login_rejects_unknown_email() -> None:
    async def run_login() -> None:
        session = FakeSession()
        auth_service = AuthService(
            session=session,
            user_repository=FakeUserRepository(existing_user=None),
            refresh_token_repository=FakeRefreshTokenRepository(),
            password_service=FakePasswordService(),
            token_service=FakeTokenService(),
        )

        with pytest.raises(AppException) as exc_info:
            await auth_service.login(LoginRequest(email="missing@example.com", password="wrong"))

        assert exc_info.value.code == error_codes.INVALID_CREDENTIALS
        assert exc_info.value.status_code == 401
        assert session.committed is False

    asyncio.run(run_login())


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
