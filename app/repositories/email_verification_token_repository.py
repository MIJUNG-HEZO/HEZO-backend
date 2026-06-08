from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.email_verification_token import EmailVerificationToken


class EmailVerificationTokenRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def revoke_active_tokens(self, *, user_id: UUID, revoked_at: datetime) -> None:
        stmt = (
            update(EmailVerificationToken)
            .where(
                EmailVerificationToken.user_id == user_id,
                EmailVerificationToken.used_at.is_(None),
                EmailVerificationToken.revoked_at.is_(None),
                EmailVerificationToken.expires_at > revoked_at,
            )
            .values(revoked_at=revoked_at)
        )
        await self.session.execute(stmt)

    async def get_by_token_hash_for_update(
        self,
        token_hash: str,
    ) -> EmailVerificationToken | None:
        stmt = (
            select(EmailVerificationToken)
            .where(EmailVerificationToken.token_hash == token_hash)
            .with_for_update()
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def mark_used(
        self,
        email_verification_token: EmailVerificationToken,
        *,
        used_at: datetime,
    ) -> EmailVerificationToken:
        email_verification_token.used_at = used_at
        await self.session.flush()
        return email_verification_token

    async def create(
        self,
        *,
        user_id: UUID,
        token_hash: str,
        expires_at: datetime,
    ) -> EmailVerificationToken:
        email_verification_token = EmailVerificationToken(
            user_id=user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            used_at=None,
            revoked_at=None,
        )
        self.session.add(email_verification_token)
        await self.session.flush()
        return email_verification_token
