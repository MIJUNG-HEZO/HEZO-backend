from dataclasses import dataclass
from datetime import datetime
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import error_codes
from app.core.config import settings
from app.core.exceptions import AppException
from app.db.session import get_db_session
from app.repositories.plan_repository import PlanRepository
from app.repositories.site_repository import SiteRepository
from app.repositories.subscription_repository import SubscriptionRepository
from app.repositories.user_repository import UserRepository
from app.services.auth_service import AuthService
from app.services.billing_service import BillingService
from app.services.email_verification_service import EmailVerificationService
from app.services.oauth_service import OAuthService
from app.services.plan_policy_service import PlanPolicyService
from app.services.plan_service import PlanService
from app.services.site_service import SiteService
from app.services.subscription_service import SubscriptionService
from app.services.token_service import TokenService
from app.services.user_service import UserService

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class CurrentUser:
    id: UUID
    email_verified_at: datetime | None

    @property
    def email_verified(self) -> bool:
        return self.email_verified_at is not None


def raise_unauthorized() -> None:
    raise AppException(
        code=error_codes.UNAUTHORIZED,
        message="Authentication is required.",
        status_code=401,
    )


def raise_invalid_token() -> None:
    raise AppException(
        code=error_codes.INVALID_TOKEN,
        message="Invalid access token.",
        status_code=401,
    )


async def require_authenticated(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> CurrentUser:
    if credentials is None:
        raise_unauthorized()

    token_service = TokenService()
    try:
        payload = token_service.decode_token(credentials.credentials)
    except jwt.ExpiredSignatureError as exc:
        raise AppException(
            code=error_codes.TOKEN_EXPIRED,
            message="Access token has expired.",
            status_code=401,
        ) from exc
    except jwt.InvalidTokenError:
        raise_invalid_token()

    if payload.get("type") != "access":
        raise_invalid_token()

    subject = payload.get("sub")
    if not isinstance(subject, str):
        raise_invalid_token()

    try:
        user_id = UUID(subject)
    except ValueError:
        raise_invalid_token()

    user = await UserRepository(session).get_by_id(user_id)
    if user is None or user.deleted_at is not None:
        raise_unauthorized()

    return CurrentUser(id=user.id, email_verified_at=user.email_verified_at)


async def require_email_verified(
    current_user: Annotated[CurrentUser, Depends(require_authenticated)],
) -> CurrentUser:
    if current_user.email_verified_at is None:
        raise AppException(
            code=error_codes.EMAIL_NOT_VERIFIED,
            message="Email verification is required.",
            status_code=403,
        )
    return current_user


def require_development_environment() -> None:
    if settings.app_env not in {"local", "dev", "test"}:
        raise AppException(
            code=error_codes.FORBIDDEN,
            message="This endpoint is only available in development environments.",
            status_code=403,
        )


def get_site_service(session: Annotated[AsyncSession, Depends(get_db_session)]) -> SiteService:
    return SiteService(session)


def get_auth_service(session: Annotated[AsyncSession, Depends(get_db_session)]) -> AuthService:
    return AuthService(session)


def get_email_verification_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> EmailVerificationService:
    return EmailVerificationService(session)


def get_oauth_service(session: Annotated[AsyncSession, Depends(get_db_session)]) -> OAuthService:
    return OAuthService(session)


def get_plan_service(session: Annotated[AsyncSession, Depends(get_db_session)]) -> PlanService:
    return PlanService(session)


def get_plan_policy_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> PlanPolicyService:
    site_repository = SiteRepository(session)
    return PlanPolicyService(
        plan_repository=PlanRepository(session),
        subscription_repository=SubscriptionRepository(session),
        site_repository=site_repository,
    )


def get_subscription_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> SubscriptionService:
    return SubscriptionService(session)


def get_billing_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> BillingService:
    return BillingService(session)


def get_user_service(session: Annotated[AsyncSession, Depends(get_db_session)]) -> UserService:
    return UserService(session)


__all__ = [
    "CurrentUser",
    "get_auth_service",
    "get_billing_service",
    "get_db_session",
    "get_email_verification_service",
    "get_oauth_service",
    "get_plan_policy_service",
    "get_plan_service",
    "get_site_service",
    "get_subscription_service",
    "get_user_service",
    "require_authenticated",
    "require_development_environment",
    "require_email_verified",
]
