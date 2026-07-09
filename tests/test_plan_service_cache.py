from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.plan import PlanListResponse, PlanResponse
from app.services.plan_service import PlanService


def _fake_plan(code: str) -> object:
    return type(
        "FakePlan",
        (),
        {
            "code": code,
            "name": "Free",
            "price_monthly": 0,
            "currency": "KRW",
            "max_sites": 1,
            "can_publish": False,
        },
    )()


@pytest.mark.asyncio
async def test_list_active_plans_falls_back_to_db_when_redis_disabled(monkeypatch) -> None:
    monkeypatch.setattr("app.services.plan_service.settings.redis_enabled", False)

    session = AsyncMock(spec=AsyncSession)
    service = PlanService(session)

    async def _list_active():
        return [_fake_plan("FREE")]

    monkeypatch.setattr(service.plan_repository, "list_active", _list_active)

    result = await service.list_active_plans()

    assert isinstance(result, PlanListResponse)
    assert result.items[0].code == "FREE"


@pytest.mark.asyncio
async def test_list_active_plans_uses_cache_hit_when_available(monkeypatch) -> None:
    monkeypatch.setattr("app.services.plan_service.settings.redis_enabled", True)

    session = AsyncMock(spec=AsyncSession)
    service = PlanService(session)

    cached_response = PlanListResponse(
        items=[
            PlanResponse(
                code="CACHED",
                name="Cached",
                price_monthly=0,
                currency="KRW",
                max_sites=1,
                can_publish=False,
            )
        ]
    )

    async def _get_cached_plans():
        return cached_response

    monkeypatch.setattr(service, "_get_cached_plans", _get_cached_plans)

    async def _list_active_should_not_be_called():
        raise AssertionError("캐시 히트 시 DB를 조회하면 안 됨")

    monkeypatch.setattr(service.plan_repository, "list_active", _list_active_should_not_be_called)

    result = await service.list_active_plans()

    assert result.items[0].code == "CACHED"
