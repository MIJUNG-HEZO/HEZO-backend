from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.plan import Plan


class PlanRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, plan_id: UUID) -> Plan | None:
        stmt = select(Plan).where(Plan.id == plan_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_code(self, code: str) -> Plan | None:
        stmt = select(Plan).where(Plan.code == code)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_free_plan(self) -> Plan | None:
        return await self.get_by_code("FREE")

    async def list_active(self) -> list[Plan]:
        stmt = (
            select(Plan)
            .where(Plan.is_active.is_(True))
            .order_by(Plan.price_monthly.asc(), Plan.code.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
