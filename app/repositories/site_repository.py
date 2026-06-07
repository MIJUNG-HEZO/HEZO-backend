from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ModuleKey, SiteStatus, SiteType
from app.models.site import Site


class SiteRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def count_active_sites_by_owner(self, owner_id: UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(Site)
            .where(
                Site.owner_id == owner_id,
                Site.deleted_at.is_(None),
                Site.status != SiteStatus.DELETED,
            )
        )
        result = await self.session.execute(stmt)
        return int(result.scalar_one())

    async def create(
        self,
        *,
        owner_id: UUID,
        name: str,
        site_type: SiteType,
        module_key: ModuleKey,
    ) -> Site:
        site = Site(
            owner_id=owner_id,
            name=name,
            site_type=site_type,
            module_key=module_key,
            status=SiteStatus.DRAFT,
            is_published=False,
        )
        self.session.add(site)
        await self.session.flush()
        return site
