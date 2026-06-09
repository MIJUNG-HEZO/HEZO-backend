from uuid import UUID

from sqlalchemy import String, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.social_account import SocialAccount


class SocialAccountRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_provider_user_id(
        self,
        *,
        provider: str,
        provider_user_id: str,
    ) -> SocialAccount | None:
        stmt = select(SocialAccount).where(
            SocialAccount.provider == provider,
            SocialAccount.provider_user_id == provider_user_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        user_id: UUID,
        provider: str,
        provider_user_id: str,
        email: str | None,
    ) -> SocialAccount:
        social_account = SocialAccount(
            user_id=user_id,
            provider=provider,
            provider_user_id=provider_user_id,
            email=email,
        )
        self.session.add(social_account)
        await self.session.flush()
        return social_account

    async def anonymize_by_user_id(self, user_id: UUID) -> None:
        stmt = (
            update(SocialAccount)
            .where(
                SocialAccount.user_id == user_id,
                SocialAccount.provider_user_id.not_like("deleted:%"),
            )
            .values(
                provider_user_id=(
                    "deleted:"
                    + SocialAccount.id.cast(String)
                    + ":"
                    + SocialAccount.provider_user_id
                ),
                email=None,
            )
        )
        await self.session.execute(stmt)
