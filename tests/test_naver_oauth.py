import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import UUID, uuid4

from fastapi.testclient import TestClient

from app.api.deps import get_oauth_service
from app.integrations.oauth.naver_oauth_client import NaverOAuthClient, NaverUserInfo
from app.main import app
from app.schemas.auth import NaverOAuthLoginRequest, OAuthCompleteSignupRequest, OAuthLoginResponse
from app.services.oauth_service import OAuthService


class FakeSession:
    def __init__(self) -> None:
        self.committed = False
        self.rolled_back = False

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


class FakeNaverOAuthClient:
    def __init__(self, user_info: NaverUserInfo) -> None:
        self.user_info = user_info
        self.code: str | None = None
        self.redirect_uri: str | None = None

    async def get_user_info_by_code(self, *, code: str, redirect_uri: str) -> NaverUserInfo:
        self.code = code
        self.redirect_uri = redirect_uri
        return self.user_info


class FakeSocialAccountRepository:
    def __init__(self, social_account: SimpleNamespace | None = None) -> None:
        self.social_account = social_account
        self.provider: str | None = None
        self.provider_user_id: str | None = None
        self.created_provider: str | None = None

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
        self.created_provider = provider
        return SimpleNamespace(
            id=uuid4(),
            user_id=user_id,
            provider=provider,
            provider_user_id=provider_user_id,
            email=email,
        )


class FakeUserRepository:
    def __init__(self, user: SimpleNamespace | None = None) -> None:
        self.user = user
        self.created_user = SimpleNamespace(
            id=uuid4(),
            email="user@example.com",
            password_hash=None,
            name="해조",
            phone=None,
            email_verified_at=None,
            created_at=datetime(2026, 6, 8, tzinfo=UTC),
            updated_at=datetime(2026, 6, 8, tzinfo=UTC),
        )

    async def get_by_id(self, user_id: UUID) -> SimpleNamespace | None:
        return self.user

    async def get_by_email(self, email: str) -> SimpleNamespace | None:
        return None

    async def create(
        self,
        *,
        email: str,
        password_hash: str | None,
        name: str,
        phone: str | None,
    ) -> SimpleNamespace:
        self.created_user.email = email
        self.created_user.password_hash = password_hash
        self.created_user.name = name
        self.created_user.phone = phone
        return self.created_user


class FakePlanRepository:
    def __init__(self) -> None:
        self.free_plan = SimpleNamespace(id=uuid4(), code="free")

    async def get_free_plan(self) -> SimpleNamespace:
        return self.free_plan


class FakeSubscriptionRepository:
    async def create_free_subscription(
        self,
        *,
        user_id: UUID,
        plan_id: UUID,
    ) -> SimpleNamespace:
        return SimpleNamespace(id=uuid4(), user_id=user_id, plan_id=plan_id)


class FakeRefreshTokenRepository:
    def __init__(self) -> None:
        self.user_id: UUID | None = None

    async def create(
        self,
        *,
        user_id: UUID,
        token_hash: str,
        expires_at: datetime,
    ) -> SimpleNamespace:
        self.user_id = user_id
        return SimpleNamespace(id=uuid4())


class FakeTokenService:
    def __init__(self) -> None:
        self.decoded_payload = {
            "type": "oauth_signup",
            "provider": "naver",
            "sub": "naver-user-id",
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
        return self.decoded_payload


class FakeOAuthService:
    def __init__(self, oauth_response: OAuthLoginResponse, refresh_token: str | None) -> None:
        self.oauth_response = oauth_response
        self.refresh_token = refresh_token
        self.payload: NaverOAuthLoginRequest | None = None

    async def login_with_naver(
        self,
        payload: NaverOAuthLoginRequest,
    ) -> tuple[OAuthLoginResponse, str | None]:
        self.payload = payload
        return self.oauth_response, self.refresh_token


def create_oauth_service(
    *,
    naver_user: NaverUserInfo,
    social_account: SimpleNamespace | None = None,
    user: SimpleNamespace | None = None,
) -> tuple[OAuthService, FakeSocialAccountRepository, FakeRefreshTokenRepository]:
    social_account_repository = FakeSocialAccountRepository(social_account=social_account)
    refresh_token_repository = FakeRefreshTokenRepository()
    oauth_service = OAuthService(
        session=FakeSession(),
        naver_oauth_client=FakeNaverOAuthClient(naver_user),
        social_account_repository=social_account_repository,
        user_repository=FakeUserRepository(user=user),
        plan_repository=FakePlanRepository(),
        subscription_repository=FakeSubscriptionRepository(),
        refresh_token_repository=refresh_token_repository,
        token_service=FakeTokenService(),
    )
    return oauth_service, social_account_repository, refresh_token_repository


def test_naver_oauth_route_returns_signup_required_response() -> None:
    fake_oauth_service = FakeOAuthService(
        OAuthLoginResponse(
            signup_required=True,
            signup_token="signup-token",
            provider="naver",
            suggested_email="user@example.com",
            suggested_name="해조",
        ),
        None,
    )
    app.dependency_overrides[get_oauth_service] = lambda: fake_oauth_service

    try:
        client = TestClient(app)
        response = client.post(
            "/api/v1/auth/oauth/naver",
            json={
                "code": " naver-code ",
                "redirect_uri": " http://localhost:3000/auth/oauth/naver/callback ",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["signup_required"] is True
    assert response.json()["provider"] == "naver"
    assert fake_oauth_service.payload is not None
    assert fake_oauth_service.payload.code == "naver-code"


def test_naver_oauth_route_sets_refresh_token_cookie_for_existing_user() -> None:
    fake_oauth_service = FakeOAuthService(
        OAuthLoginResponse(signup_required=False, access_token="access-token"),
        "refresh-token",
    )
    app.dependency_overrides[get_oauth_service] = lambda: fake_oauth_service

    try:
        client = TestClient(app)
        response = client.post(
            "/api/v1/auth/oauth/naver",
            json={
                "code": "naver-code",
                "redirect_uri": "http://localhost:3000/auth/oauth/naver/callback",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["signup_required"] is False
    assert response.json()["access_token"] == "access-token"
    assert response.cookies.get("refresh_token") == "refresh-token"
    assert "HttpOnly" in response.headers["set-cookie"]


def test_oauth_service_returns_signup_token_for_new_naver_account() -> None:
    async def run_login() -> None:
        oauth_service, social_account_repository, _ = create_oauth_service(
            naver_user=NaverUserInfo(
                provider_user_id="naver-user-id",
                email="user@example.com",
                name="해조",
            )
        )

        response, refresh_token = await oauth_service.login_with_naver(
            NaverOAuthLoginRequest(
                code="naver-code",
                redirect_uri="http://localhost:3000/auth/oauth/naver/callback",
            )
        )

        assert response.signup_required is True
        assert response.signup_token == "signup-token-naver-naver-user-id-user@example.com-해조"
        assert response.provider == "naver"
        assert response.suggested_email == "user@example.com"
        assert response.suggested_name == "해조"
        assert refresh_token is None
        assert social_account_repository.provider == "naver"
        assert social_account_repository.provider_user_id == "naver-user-id"

    asyncio.run(run_login())


def test_oauth_service_logs_in_existing_naver_account() -> None:
    async def run_login() -> None:
        user_id = uuid4()
        oauth_service, social_account_repository, refresh_token_repository = create_oauth_service(
            naver_user=NaverUserInfo(
                provider_user_id="naver-user-id",
                email=None,
                name=None,
            ),
            social_account=SimpleNamespace(user_id=user_id),
            user=SimpleNamespace(id=user_id, deleted_at=None),
        )

        response, refresh_token = await oauth_service.login_with_naver(
            NaverOAuthLoginRequest(
                code="naver-code",
                redirect_uri="http://localhost:3000/auth/oauth/naver/callback",
            )
        )

        assert response.signup_required is False
        assert response.access_token == f"access-token-for-{user_id}"
        assert refresh_token == "refresh-token"
        assert social_account_repository.provider == "naver"
        assert refresh_token_repository.user_id == user_id

    asyncio.run(run_login())


def test_oauth_service_complete_signup_accepts_naver_signup_token() -> None:
    async def run_complete_signup() -> None:
        oauth_service, social_account_repository, _ = create_oauth_service(
            naver_user=NaverUserInfo(provider_user_id="naver-user-id", email=None, name=None)
        )

        response, refresh_token = await oauth_service.complete_signup(
            OAuthCompleteSignupRequest(
                signup_token="signup-token",
                email="user@example.com",
                name="해조",
            )
        )

        assert response.signup_required is False
        assert response.access_token is not None
        assert refresh_token == "refresh-token"
        assert social_account_repository.created_provider == "naver"

    asyncio.run(run_complete_signup())


def test_naver_client_parses_response_email_and_name() -> None:
    user_info = NaverOAuthClient()._parse_user_info(
        {
            "resultcode": "00",
            "message": "success",
            "response": {
                "id": "naver-user-id",
                "email": "user@example.com",
                "name": "해조",
            },
        }
    )

    assert user_info == NaverUserInfo(
        provider_user_id="naver-user-id",
        email="user@example.com",
        name="해조",
    )
