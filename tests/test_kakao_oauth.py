import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_oauth_service
from app.core import error_codes
from app.core.exceptions import AppException
from app.integrations.oauth.kakao_oauth_client import KakaoOAuthClient, KakaoUserInfo
from app.main import app
from app.schemas.auth import KakaoOAuthLoginRequest, OAuthCompleteSignupRequest, OAuthLoginResponse
from app.services.oauth_service import OAuthService


class FakeSession:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


class FakeKakaoOAuthClient:
    def __init__(self, user_info: KakaoUserInfo) -> None:
        self.user_info = user_info
        self.code: str | None = None
        self.redirect_uri: str | None = None

    async def get_user_info_by_code(self, *, code: str, redirect_uri: str) -> KakaoUserInfo:
        self.code = code
        self.redirect_uri = redirect_uri
        return self.user_info


class FakeSocialAccountRepository:
    def __init__(self, social_account: SimpleNamespace | None = None) -> None:
        self.social_account = social_account
        self.provider: str | None = None
        self.provider_user_id: str | None = None
        self.created_user_id: UUID | None = None
        self.created_provider: str | None = None
        self.created_provider_user_id: str | None = None
        self.created_email: str | None = None

    async def get_by_provider_user_id(
        self,
        *,
        provider: str,
        provider_user_id: str,
    ) -> SimpleNamespace | None:
        self.provider = provider
        self.provider_user_id = provider_user_id
        return self.social_account

    async def create(
        self,
        *,
        user_id: UUID,
        provider: str,
        provider_user_id: str,
        email: str | None,
    ) -> SimpleNamespace:
        self.created_user_id = user_id
        self.created_provider = provider
        self.created_provider_user_id = provider_user_id
        self.created_email = email
        return SimpleNamespace(id=uuid4())


class FakeUserRepository:
    def __init__(
        self,
        user: SimpleNamespace | None = None,
        existing_email_user: SimpleNamespace | None = None,
    ) -> None:
        self.user = user
        self.existing_email_user = existing_email_user
        self.user_id: UUID | None = None
        self.email: str | None = None
        self.created_user: SimpleNamespace | None = None

    async def get_by_id(self, user_id: UUID) -> SimpleNamespace | None:
        self.user_id = user_id
        return self.user

    async def get_by_email(self, email: str) -> SimpleNamespace | None:
        self.email = email
        return self.existing_email_user

    async def create(
        self,
        *,
        email: str,
        password_hash: str | None,
        name: str,
        phone: str | None,
    ) -> SimpleNamespace:
        self.created_user = SimpleNamespace(
            id=uuid4(),
            email=email,
            password_hash=password_hash,
            name=name,
            phone=phone,
            email_verified_at=None,
            created_at=datetime(2026, 6, 8, tzinfo=UTC),
            updated_at=datetime(2026, 6, 8, tzinfo=UTC),
        )
        return self.created_user


class FakePlanRepository:
    def __init__(self, free_plan: SimpleNamespace | None = None) -> None:
        self.free_plan = free_plan or SimpleNamespace(id=uuid4(), code="free")
        self.free_plan_requested = False

    async def get_free_plan(self) -> SimpleNamespace | None:
        self.free_plan_requested = True
        return self.free_plan


class FakeSubscriptionRepository:
    def __init__(self) -> None:
        self.user_id: UUID | None = None
        self.plan_id: UUID | None = None

    async def create_free_subscription(
        self,
        *,
        user_id: UUID,
        plan_id: UUID,
    ) -> SimpleNamespace:
        self.user_id = user_id
        self.plan_id = plan_id
        return SimpleNamespace(id=uuid4(), user_id=user_id, plan_id=plan_id)


class FakeRefreshTokenRepository:
    def __init__(self) -> None:
        self.user_id: UUID | None = None
        self.token_hash: str | None = None
        self.expires_at: datetime | None = None

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


class FakeTokenService:
    def __init__(self) -> None:
        self.decoded_payload = {
            "type": "oauth_signup",
            "provider": "kakao",
            "sub": "12345",
        }

    def create_access_token(self, *, user_id: UUID) -> str:
        return f"access-token-for-{user_id}"

    def create_refresh_token(self) -> str:
        return "refresh-token"

    def hash_refresh_token(self, refresh_token: str) -> str:
        return f"hashed-{refresh_token}"

    def get_refresh_token_expires_at(self) -> datetime:
        return datetime(2026, 6, 22, tzinfo=UTC)

    def create_oauth_signup_token(
        self,
        *,
        provider: str,
        provider_user_id: str,
        email: str | None,
        name: str | None,
    ) -> str:
        return f"signup-token-{provider}-{provider_user_id}-{email}-{name}"

    def decode_oauth_signup_token(self, token: str) -> dict:
        if token == "invalid-signup-token":
            raise Exception("invalid token")
        return self.decoded_payload


class FakeOAuthService:
    def __init__(self, oauth_response: OAuthLoginResponse, refresh_token: str | None) -> None:
        self.oauth_response = oauth_response
        self.refresh_token = refresh_token
        self.payload: KakaoOAuthLoginRequest | None = None
        self.complete_signup_payload: OAuthCompleteSignupRequest | None = None

    async def login_with_kakao(
        self,
        payload: KakaoOAuthLoginRequest,
    ) -> tuple[OAuthLoginResponse, str | None]:
        self.payload = payload
        return self.oauth_response, self.refresh_token

    async def complete_signup(
        self,
        payload: OAuthCompleteSignupRequest,
    ) -> tuple[OAuthLoginResponse, str]:
        self.complete_signup_payload = payload
        return self.oauth_response, self.refresh_token or "refresh-token"


def test_kakao_oauth_route_returns_signup_required_response() -> None:
    fake_oauth_service = FakeOAuthService(
        OAuthLoginResponse(
            signup_required=True,
            signup_token="signup-token",
            provider="kakao",
            suggested_email="user@example.com",
            suggested_name="해조",
        ),
        None,
    )
    app.dependency_overrides[get_oauth_service] = lambda: fake_oauth_service

    try:
        client = TestClient(app)
        response = client.post(
            "/api/v1/auth/oauth/kakao",
            json={
                "code": " kakao-code ",
                "redirect_uri": " http://localhost:3000/oauth/kakao/callback ",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "signup_required": True,
        "access_token": None,
        "token_type": "bearer",
        "signup_token": "signup-token",
        "provider": "kakao",
        "suggested_email": "user@example.com",
        "suggested_name": "해조",
    }
    assert response.cookies.get("refresh_token") is None
    assert fake_oauth_service.payload is not None
    assert fake_oauth_service.payload.code == "kakao-code"


def test_kakao_oauth_route_sets_refresh_token_cookie_for_existing_user() -> None:
    fake_oauth_service = FakeOAuthService(
        OAuthLoginResponse(signup_required=False, access_token="access-token"),
        "refresh-token",
    )
    app.dependency_overrides[get_oauth_service] = lambda: fake_oauth_service

    try:
        client = TestClient(app)
        response = client.post(
            "/api/v1/auth/oauth/kakao",
            json={
                "code": "kakao-code",
                "redirect_uri": "http://localhost:3000/oauth/kakao/callback",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "signup_required": False,
        "access_token": "access-token",
        "token_type": "bearer",
        "signup_token": None,
        "provider": None,
        "suggested_email": None,
        "suggested_name": None,
    }
    assert response.cookies.get("refresh_token") == "refresh-token"
    assert "HttpOnly" in response.headers["set-cookie"]


def test_complete_oauth_signup_route_sets_refresh_token_cookie() -> None:
    fake_oauth_service = FakeOAuthService(
        OAuthLoginResponse(signup_required=False, access_token="access-token"),
        "refresh-token",
    )
    app.dependency_overrides[get_oauth_service] = lambda: fake_oauth_service

    try:
        client = TestClient(app)
        response = client.post(
            "/api/v1/auth/oauth/complete-signup",
            json={
                "signup_token": " signup-token ",
                "email": "User@Example.com",
                "name": " 해조 ",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "signup_required": False,
        "access_token": "access-token",
        "token_type": "bearer",
        "signup_token": None,
        "provider": None,
        "suggested_email": None,
        "suggested_name": None,
    }
    assert response.cookies.get("refresh_token") == "refresh-token"
    assert fake_oauth_service.complete_signup_payload is not None
    assert fake_oauth_service.complete_signup_payload.signup_token == "signup-token"
    assert fake_oauth_service.complete_signup_payload.email == "user@example.com"
    assert fake_oauth_service.complete_signup_payload.name == "해조"


def test_complete_oauth_signup_route_rejects_invalid_email_format() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/v1/auth/oauth/complete-signup",
        json={
            "signup_token": "signup-token",
            "email": "not-an-email",
            "name": "해조",
        },
    )

    assert response.status_code == 422


def test_complete_oauth_signup_route_rejects_name_with_number() -> None:
    client = TestClient(app)

    response = client.post(
        "/api/v1/auth/oauth/complete-signup",
        json={
            "signup_token": "signup-token",
            "email": "user@example.com",
            "name": "해조123",
        },
    )

    assert response.status_code == 422


def test_oauth_service_returns_signup_token_for_new_kakao_account() -> None:
    async def run_login() -> None:
        kakao_client = FakeKakaoOAuthClient(
            KakaoUserInfo(
                provider_user_id="12345",
                email="user@example.com",
                name="해조",
            )
        )
        social_account_repository = FakeSocialAccountRepository(social_account=None)
        oauth_service = OAuthService(
            session=FakeSession(),
            kakao_oauth_client=kakao_client,
            social_account_repository=social_account_repository,
            user_repository=FakeUserRepository(),
            refresh_token_repository=FakeRefreshTokenRepository(),
            token_service=FakeTokenService(),
        )

        response, refresh_token = await oauth_service.login_with_kakao(
            KakaoOAuthLoginRequest(
                code="kakao-code",
                redirect_uri="http://localhost:3000/oauth/kakao/callback",
            )
        )

        assert response.signup_required is True
        assert response.signup_token == "signup-token-kakao-12345-user@example.com-해조"
        assert response.provider == "kakao"
        assert response.suggested_email == "user@example.com"
        assert response.suggested_name == "해조"
        assert refresh_token is None
        assert kakao_client.code == "kakao-code"
        assert social_account_repository.provider == "kakao"
        assert social_account_repository.provider_user_id == "12345"

    asyncio.run(run_login())


def test_oauth_service_complete_signup_creates_user_social_account_and_tokens() -> None:
    async def run_complete_signup() -> None:
        session = FakeSession()
        user_repository = FakeUserRepository()
        plan_repository = FakePlanRepository()
        subscription_repository = FakeSubscriptionRepository()
        social_account_repository = FakeSocialAccountRepository(social_account=None)
        refresh_token_repository = FakeRefreshTokenRepository()
        oauth_service = OAuthService(
            session=session,
            kakao_oauth_client=FakeKakaoOAuthClient(
                KakaoUserInfo(provider_user_id="12345", email=None, name=None)
            ),
            social_account_repository=social_account_repository,
            user_repository=user_repository,
            plan_repository=plan_repository,
            subscription_repository=subscription_repository,
            refresh_token_repository=refresh_token_repository,
            token_service=FakeTokenService(),
        )

        response, refresh_token = await oauth_service.complete_signup(
            OAuthCompleteSignupRequest(
                signup_token="signup-token",
                email="user@example.com",
                name="해조",
            )
        )

        assert response.signup_required is False
        assert response.access_token == f"access-token-for-{user_repository.created_user.id}"
        assert refresh_token == "refresh-token"
        assert user_repository.created_user is not None
        assert user_repository.created_user.password_hash is None
        assert plan_repository.free_plan_requested is True
        assert subscription_repository.user_id == user_repository.created_user.id
        assert subscription_repository.plan_id == plan_repository.free_plan.id
        assert social_account_repository.created_user_id == user_repository.created_user.id
        assert social_account_repository.created_provider == "kakao"
        assert social_account_repository.created_provider_user_id == "12345"
        assert social_account_repository.created_email == "user@example.com"
        assert refresh_token_repository.user_id == user_repository.created_user.id
        assert refresh_token_repository.token_hash == "hashed-refresh-token"
        assert session.committed is True
        assert session.rolled_back is False

    asyncio.run(run_complete_signup())


def test_oauth_service_complete_signup_rejects_duplicate_email() -> None:
    async def run_complete_signup() -> None:
        session = FakeSession()
        oauth_service = OAuthService(
            session=session,
            kakao_oauth_client=FakeKakaoOAuthClient(
                KakaoUserInfo(provider_user_id="12345", email=None, name=None)
            ),
            social_account_repository=FakeSocialAccountRepository(social_account=None),
            user_repository=FakeUserRepository(existing_email_user=SimpleNamespace(id=uuid4())),
            plan_repository=FakePlanRepository(),
            subscription_repository=FakeSubscriptionRepository(),
            refresh_token_repository=FakeRefreshTokenRepository(),
            token_service=FakeTokenService(),
        )

        with pytest.raises(AppException) as exc_info:
            await oauth_service.complete_signup(
                OAuthCompleteSignupRequest(
                    signup_token="signup-token",
                    email="user@example.com",
                    name="해조",
                )
            )

        assert exc_info.value.code == error_codes.EMAIL_ALREADY_EXISTS
        assert exc_info.value.status_code == 409
        assert session.committed is False

    asyncio.run(run_complete_signup())


def test_oauth_service_logs_in_existing_kakao_account() -> None:
    async def run_login() -> None:
        user_id = uuid4()
        session = FakeSession()
        refresh_token_repository = FakeRefreshTokenRepository()
        oauth_service = OAuthService(
            session=session,
            kakao_oauth_client=FakeKakaoOAuthClient(
                KakaoUserInfo(
                    provider_user_id="12345",
                    email=None,
                    name=None,
                )
            ),
            social_account_repository=FakeSocialAccountRepository(
                social_account=SimpleNamespace(user_id=user_id)
            ),
            user_repository=FakeUserRepository(
                user=SimpleNamespace(id=user_id, deleted_at=None)
            ),
            refresh_token_repository=refresh_token_repository,
            token_service=FakeTokenService(),
        )

        response, refresh_token = await oauth_service.login_with_kakao(
            KakaoOAuthLoginRequest(
                code="kakao-code",
                redirect_uri="http://localhost:3000/oauth/kakao/callback",
            )
        )

        assert response.signup_required is False
        assert response.access_token == f"access-token-for-{user_id}"
        assert refresh_token == "refresh-token"
        assert refresh_token_repository.user_id == user_id
        assert refresh_token_repository.token_hash == "hashed-refresh-token"
        assert refresh_token_repository.expires_at == datetime(2026, 6, 22, tzinfo=UTC)
        assert session.committed is True

    asyncio.run(run_login())


def test_oauth_service_rejects_connected_deleted_user() -> None:
    async def run_login() -> None:
        user_id = uuid4()
        oauth_service = OAuthService(
            session=FakeSession(),
            kakao_oauth_client=FakeKakaoOAuthClient(
                KakaoUserInfo(provider_user_id="12345", email=None, name=None)
            ),
            social_account_repository=FakeSocialAccountRepository(
                social_account=SimpleNamespace(user_id=user_id)
            ),
            user_repository=FakeUserRepository(
                user=SimpleNamespace(id=user_id, deleted_at=datetime(2026, 6, 8, tzinfo=UTC))
            ),
            refresh_token_repository=FakeRefreshTokenRepository(),
            token_service=FakeTokenService(),
        )

        with pytest.raises(AppException) as exc_info:
            await oauth_service.login_with_kakao(
                KakaoOAuthLoginRequest(
                    code="kakao-code",
                    redirect_uri="http://localhost:3000/oauth/kakao/callback",
                )
            )

        assert exc_info.value.code == error_codes.UNAUTHORIZED
        assert exc_info.value.status_code == 401

    asyncio.run(run_login())


def test_kakao_client_parses_account_email_and_profile_nickname() -> None:
    user_info = KakaoOAuthClient()._parse_user_info(
        {
            "id": 12345,
            "kakao_account": {
                "email": "user@example.com",
                "profile": {"nickname": "해조"},
            },
        }
    )

    assert user_info == KakaoUserInfo(
        provider_user_id="12345",
        email="user@example.com",
        name="해조",
    )
