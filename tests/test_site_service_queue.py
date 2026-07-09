from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from unittest.mock import AsyncMock

from app.core.site_queue_publisher import FakeSiteQueuePublisher
from app.core.site_queue_tracker import FakeSiteQueueTracker
from app.schemas.site import SiteCreateAcceptedResponse, SiteCreateRequest, SiteResponse
from app.services.site_service import SiteService


def _make_service(*, publisher: FakeSiteQueuePublisher, tracker: FakeSiteQueueTracker) -> SiteService:
    session = AsyncMock(spec=AsyncSession)
    service = SiteService(session, queue_publisher=publisher, queue_tracker=tracker)
    return service


@pytest.mark.asyncio
async def test_create_site_returns_202_shape_when_publish_succeeds(monkeypatch) -> None:
    publisher = FakeSiteQueuePublisher(should_succeed=True)
    tracker = FakeSiteQueueTracker()
    service = _make_service(publisher=publisher, tracker=tracker)

    async def _require_can_create_site(user_id: UUID) -> None:
        return None

    monkeypatch.setattr(
        service.plan_policy_service, "require_can_create_site", _require_can_create_site,
    )

    payload = SiteCreateRequest(name="강남 한의원", site_type="landing", module_key="medical")
    result = await service.create_site(user_id=uuid4(), email_verified=True, payload=payload)

    assert isinstance(result, SiteCreateAcceptedResponse)
    assert result.status == "queued"
    assert len(publisher.published) == 1
    assert publisher.published[0]["name"] == "강남 한의원"
    # DynamoDB 추적 레코드도 같은 id로 기록됐어야 함
    record = await tracker.get_record(site_id=result.id)
    assert record is not None
    assert record["status"] == "queued"


@pytest.mark.asyncio
async def test_create_site_falls_back_to_sync_insert_when_publish_fails(monkeypatch) -> None:
    publisher = FakeSiteQueuePublisher(should_succeed=False)
    tracker = FakeSiteQueueTracker()
    service = _make_service(publisher=publisher, tracker=tracker)

    async def _require_can_create_site(user_id: UUID) -> None:
        return None

    monkeypatch.setattr(
        service.plan_policy_service, "require_can_create_site", _require_can_create_site,
    )

    fake_site = type(
        "FakeSite",
        (),
        {
            "id": uuid4(),
            "name": "강남 한의원",
            "site_type": "landing",
            "module_key": "medical",
            "status": "draft",
            "is_published": False,
            "published_at": None,
            "created_at": datetime(2026, 6, 7, tzinfo=UTC),
            "updated_at": datetime(2026, 6, 7, tzinfo=UTC),
        },
    )()

    async def _create(**kwargs):
        return fake_site

    monkeypatch.setattr(service.site_repository, "create", _create)

    payload = SiteCreateRequest(name="강남 한의원", site_type="landing", module_key="medical")
    result = await service.create_site(user_id=uuid4(), email_verified=True, payload=payload)

    assert isinstance(result, SiteResponse)
    assert result.name == "강남 한의원"
    # 발행은 시도됐지만(실패) DynamoDB 추적 기록은 안 남아야 함(폴백 경로는 큐 상태가 아니므로)
    record = await tracker.get_record(site_id=result.id)
    assert record is None
