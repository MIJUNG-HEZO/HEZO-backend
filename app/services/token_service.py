from datetime import UTC, datetime, timedelta
from secrets import token_urlsafe
from uuid import UUID

import jwt

from app.core.config import settings


class TokenService:
    def create_access_token(self, *, user_id: UUID) -> str:
        now = datetime.now(UTC)
        expires_at = now + timedelta(minutes=settings.access_token_expires_minutes)
        payload = {
            "sub": str(user_id),
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
            "type": "access",
        }
        return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)

    def create_refresh_token(self) -> str:
        return token_urlsafe(64)

    def hash_refresh_token(self, refresh_token: str) -> str:
        import hashlib

        return hashlib.sha256(refresh_token.encode("utf-8")).hexdigest()

    def get_refresh_token_expires_at(self) -> datetime:
        return datetime.now(UTC) + timedelta(days=settings.refresh_token_expires_days)
