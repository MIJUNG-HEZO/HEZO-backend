from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, user_id: UUID) -> User | None:
        stmt = select(User).where(User.id == user_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id_for_update(self, user_id: UUID) -> User | None:
        stmt = select(User).where(User.id == user_id).with_for_update()
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == email)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def mark_email_verified(self, user: User, *, verified_at: datetime) -> User:
        user.email_verified_at = verified_at
        await self.session.flush()
        return user

    async def soft_delete(self, user: User, *, deleted_at: datetime) -> User:
        user.deleted_at = deleted_at
        user.email = f"deleted:{user.id}:{user.email}"
        user.password_hash = None
        user.phone = None
        await self.session.flush()
        return user

    async def create(
        self,
        *,
        email: str,
        password_hash: str | None,
        name: str,
        phone: str | None,
    ) -> User:
        user = User(
            email=email,
            password_hash=password_hash,
            name=name,
            phone=phone,
            email_verified_at=None,
        )
        self.session.add(user)
        await self.session.flush()
        return user
