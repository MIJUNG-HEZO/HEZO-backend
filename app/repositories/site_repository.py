from datetime import UTC, datetime
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

    async def count_published_sites_by_owner(self, owner_id: UUID) -> int:
        """발행된(is_published=True) 사이트 수만 카운트 — 플랜 발행 한도 체크용."""
        stmt = (
            select(func.count())
            .select_from(Site)
            .where(
                Site.owner_id == owner_id,
                Site.is_published.is_(True),
                Site.deleted_at.is_(None),
                Site.status != SiteStatus.DELETED,
            )
        )
        result = await self.session.execute(stmt)
        return int(result.scalar_one())

    async def list_active_sites_by_owner(self, owner_id: UUID) -> list[Site]:
        stmt = (
            select(Site)
            .where(
                Site.owner_id == owner_id,
                Site.deleted_at.is_(None),
                Site.status != SiteStatus.DELETED,
            )
            .order_by(Site.created_at.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_active_site_by_id_and_owner(
        self,
        *,
        site_id: UUID,
        owner_id: UUID,
    ) -> Site | None:
        stmt = select(Site).where(
            Site.id == site_id,
            Site.owner_id == owner_id,
            Site.deleted_at.is_(None),
            Site.status != SiteStatus.DELETED,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

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

    async def update_basic_info(
        self,
        *,
        site: Site,
        name: str,
        site_type: SiteType,
        module_key: ModuleKey,
    ) -> Site:
        site.name = name
        site.site_type = site_type
        site.module_key = module_key
        await self.session.flush()
        return site

    async def publish(self, *, site: Site) -> Site:
        site.is_published = True
        site.published_at = datetime.now(UTC)
        await self.session.flush()
        return site

    async def soft_delete(self, *, site: Site) -> Site:
        site.status = SiteStatus.DELETED
        site.deleted_at = datetime.now(UTC)
        await self.session.flush()
        return site
