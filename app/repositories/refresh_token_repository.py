from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.refresh_token import RefreshToken


class RefreshTokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_token_hash_for_update(self, token_hash: str) -> RefreshToken | None:
        stmt = select(RefreshToken).where(RefreshToken.token_hash == token_hash).with_for_update()
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def revoke(self, refresh_token: RefreshToken, *, revoked_at: datetime) -> RefreshToken:
        refresh_token.revoked_at = revoked_at
        await self.session.flush()
        return refresh_token

    async def create(
        self,
        *,
        user_id: UUID,
        token_hash: str,
        expires_at: datetime,
    ) -> RefreshToken:
        refresh_token = RefreshToken(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            revoked_at=None,
        )
        self.session.add(refresh_token)
        await self.session.flush()
        return refresh_token
