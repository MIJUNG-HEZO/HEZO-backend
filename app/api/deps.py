from dataclasses import dataclass
from datetime import datetime
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import error_codes
from app.core.exceptions import AppException
from app.db.session import get_db_session
from app.repositories.user_repository import UserRepository
from app.services.auth_service import AuthService
from app.services.plan_service import PlanService
from app.services.site_service import SiteService
from app.services.token_service import TokenService

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


def get_site_service(session: Annotated[AsyncSession, Depends(get_db_session)]) -> SiteService:
    return SiteService(session)


def get_auth_service(session: Annotated[AsyncSession, Depends(get_db_session)]) -> AuthService:
    return AuthService(session)


def get_plan_service(session: Annotated[AsyncSession, Depends(get_db_session)]) -> PlanService:
    return PlanService(session)


__all__ = [
    "CurrentUser",
    "get_auth_service",
    "get_db_session",
    "get_plan_service",
    "get_site_service",
    "require_authenticated",
    "require_email_verified",
]
