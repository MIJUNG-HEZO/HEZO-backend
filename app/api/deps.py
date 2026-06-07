from dataclasses import dataclass
from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import error_codes
from app.core.exceptions import AppException
from app.db.session import get_db_session
from app.services.auth_service import AuthService
from app.services.site_service import SiteService


@dataclass(frozen=True)
class CurrentUser:
    id: UUID
    email_verified_at: datetime | None

    @property
    def email_verified(self) -> bool:
        return self.email_verified_at is not None


async def require_authenticated() -> CurrentUser:
    raise AppException(
        code=error_codes.UNAUTHORIZED,
        message="Authentication is required.",
        status_code=401,
    )


async def require_email_verified() -> CurrentUser:
    return await require_authenticated()


def get_site_service(session: Annotated[AsyncSession, Depends(get_db_session)]) -> SiteService:
    return SiteService(session)


def get_auth_service(session: Annotated[AsyncSession, Depends(get_db_session)]) -> AuthService:
    return AuthService(session)


__all__ = [
    "CurrentUser",
    "get_auth_service",
    "get_db_session",
    "get_site_service",
    "require_authenticated",
    "require_email_verified",
]
