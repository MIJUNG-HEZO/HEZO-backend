import jwt
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import error_codes
from app.core.exceptions import AppException
from app.integrations.oauth.kakao_oauth_client import KakaoOAuthClient
from app.integrations.oauth.naver_oauth_client import NaverOAuthClient
from app.repositories.plan_repository import PlanRepository
from app.repositories.refresh_token_repository import RefreshTokenRepository
from app.repositories.social_account_repository import SocialAccountRepository
from app.repositories.subscription_repository import SubscriptionRepository
from app.repositories.user_repository import UserRepository
from app.schemas.auth import (
    KakaoOAuthLoginRequest,
    NaverOAuthLoginRequest,
    OAuthCompleteSignupRequest,
    OAuthLoginResponse,
)
from app.services.token_service import TokenService

SUPPORTED_OAUTH_PROVIDERS = frozenset({"kakao", "naver"})


class OAuthService:
    def __init__(
        self,
        session: AsyncSession,
        kakao_oauth_client: KakaoOAuthClient | None = None,
        naver_oauth_client: NaverOAuthClient | None = None,
        social_account_repository: SocialAccountRepository | None = None,
        user_repository: UserRepository | None = None,
        plan_repository: PlanRepository | None = None,
        subscription_repository: SubscriptionRepository | None = None,
        refresh_token_repository: RefreshTokenRepository | None = None,
        token_service: TokenService | None = None,
    ) -> None:
        self.session = session
        self.kakao_oauth_client = kakao_oauth_client or KakaoOAuthClient()
        self.naver_oauth_client = naver_oauth_client or NaverOAuthClient()
        self.social_account_repository = social_account_repository or SocialAccountRepository(
            session
        )
        self.user_repository = user_repository or UserRepository(session)
        self.plan_repository = plan_repository or PlanRepository(session)
        self.subscription_repository = subscription_repository or SubscriptionRepository(session)
        self.refresh_token_repository = refresh_token_repository or RefreshTokenRepository(session)
        self.token_service = token_service or TokenService()

    async def login_with_kakao(
        self,
        payload: KakaoOAuthLoginRequest,
    ) -> tuple[OAuthLoginResponse, str | None]:
        kakao_user = await self.kakao_oauth_client.get_user_info_by_code(
            code=payload.code,
            redirect_uri=payload.redirect_uri,
        )
        return await self._login_with_provider(
            provider="kakao",
            provider_user_id=kakao_user.provider_user_id,
            email=kakao_user.email,
            name=kakao_user.name,
        )

    async def login_with_naver(
        self,
        payload: NaverOAuthLoginRequest,
    ) -> tuple[OAuthLoginResponse, str | None]:
        naver_user = await self.naver_oauth_client.get_user_info_by_code(
            code=payload.code,
            redirect_uri=payload.redirect_uri,
        )
        return await self._login_with_provider(
            provider="naver",
            provider_user_id=naver_user.provider_user_id,
            email=naver_user.email,
            name=naver_user.name,
        )

    async def _login_with_provider(
        self,
        *,
        provider: str,
        provider_user_id: str,
        email: str | None,
        name: str | None,
    ) -> tuple[OAuthLoginResponse, str | None]:
        social_account = await self.social_account_repository.get_by_provider_user_id(
            provider=provider,
            provider_user_id=provider_user_id,
        )

        if social_account is None:
            signup_token = self.token_service.create_oauth_signup_token(
                provider=provider,
                provider_user_id=provider_user_id,
                email=email,
                name=name,
            )
            return (
                OAuthLoginResponse(
                    signup_required=True,
                    signup_token=signup_token,
                    provider=provider,
                    suggested_email=email,
                    suggested_name=name,
                ),
                None,
            )

        user = await self.user_repository.get_by_id(social_account.user_id)
        if user is None or user.deleted_at is not None:
            raise AppException(
                code=error_codes.UNAUTHORIZED,
                message="Connected social account user is not available.",
                status_code=401,
            )

        access_token = self.token_service.create_access_token(user_id=user.id)
        refresh_token = self.token_service.create_refresh_token()
        refresh_token_hash = self.token_service.hash_refresh_token(refresh_token)
        refresh_token_expires_at = self.token_service.get_refresh_token_expires_at()

        try:
            await self.refresh_token_repository.create(
                user_id=user.id,
                token_hash=refresh_token_hash,
                expires_at=refresh_token_expires_at,
            )
            await self.session.commit()
        except SQLAlchemyError:
            await self.session.rollback()
            raise

        return OAuthLoginResponse(signup_required=False, access_token=access_token), refresh_token

    async def complete_signup(
        self,
        payload: OAuthCompleteSignupRequest,
    ) -> tuple[OAuthLoginResponse, str]:
        signup_payload = self._decode_signup_token(payload.signup_token)
        provider = signup_payload["provider"]
        provider_user_id = signup_payload["provider_user_id"]

        existing_user = await self.user_repository.get_by_email(payload.email)
        if existing_user is not None:
            raise AppException(
                code=error_codes.EMAIL_ALREADY_EXISTS,
                message="Email already exists.",
                status_code=409,
                details={"email": payload.email},
            )

        existing_social_account = await self.social_account_repository.get_by_provider_user_id(
            provider=provider,
            provider_user_id=provider_user_id,
        )
        if existing_social_account is not None:
            raise AppException(
                code=error_codes.CONFLICT,
                message="Social account is already connected.",
                status_code=409,
            )

        try:
            user = await self.user_repository.create(
                email=payload.email,
                password_hash=None,
                name=payload.name,
                phone=None,
            )
            free_plan = await self.plan_repository.get_free_plan()
            if free_plan is None:
                await self.session.rollback()
                raise AppException(
                    code=error_codes.PLAN_NOT_FOUND,
                    message="Free plan is not configured.",
                    status_code=500,
                )

            await self.subscription_repository.create_free_subscription(
                user_id=user.id,
                plan_id=free_plan.id,
            )
            await self.social_account_repository.create(
                user_id=user.id,
                provider=provider,
                provider_user_id=provider_user_id,
                email=payload.email,
            )

            access_token = self.token_service.create_access_token(user_id=user.id)
            refresh_token = self.token_service.create_refresh_token()
            await self.refresh_token_repository.create(
                user_id=user.id,
                token_hash=self.token_service.hash_refresh_token(refresh_token),
                expires_at=self.token_service.get_refresh_token_expires_at(),
            )
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise AppException(
                code=error_codes.CONFLICT,
                message="OAuth signup conflicts with existing data.",
                status_code=409,
            ) from exc
        except SQLAlchemyError:
            await self.session.rollback()
            raise

        return OAuthLoginResponse(signup_required=False, access_token=access_token), refresh_token

    def _decode_signup_token(self, signup_token: str) -> dict[str, str]:
        try:
            payload = self.token_service.decode_oauth_signup_token(signup_token)
        except jwt.InvalidTokenError as exc:
            raise AppException(
                code=error_codes.INVALID_OAUTH_SIGNUP_TOKEN,
                message="Invalid OAuth signup token.",
                status_code=401,
            ) from exc

        provider = payload.get("provider")
        provider_user_id = payload.get("sub")
        if provider not in SUPPORTED_OAUTH_PROVIDERS or not isinstance(provider_user_id, str):
            raise AppException(
                code=error_codes.INVALID_OAUTH_SIGNUP_TOKEN,
                message="Invalid OAuth signup token.",
                status_code=401,
            )
        return {"provider": provider, "provider_user_id": provider_user_id}
