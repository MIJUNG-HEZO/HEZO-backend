import asyncio
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.api.deps import get_plan_service
from app.main import app
from app.schemas.plan import PlanListResponse
from app.services.plan_service import PlanService


class FakePlanService:
    async def list_active_plans(self) -> PlanListResponse:
        return PlanListResponse(
            items=[
                SimpleNamespace(
                    code="FREE",
                    name="Free",
                    price_monthly=0,
                    currency="KRW",
                    max_sites=1,
                    can_publish=False,
                ),
                SimpleNamespace(
                    code="PRO",
                    name="Pro",
                    price_monthly=29000,
                    currency="KRW",
                    max_sites=1,
                    can_publish=True,
                ),
                SimpleNamespace(
                    code="MAX",
                    name="Max",
                    price_monthly=99000,
                    currency="KRW",
                    max_sites=4,
                    can_publish=True,
                ),
            ]
        )


class FakePlanRepository:
    async def list_active(self) -> list[SimpleNamespace]:
        return [
            SimpleNamespace(
                code="FREE",
                name="Free",
                price_monthly=0,
                currency="KRW",
                max_sites=1,
                can_publish=False,
            ),
            SimpleNamespace(
                code="PRO",
                name="Pro",
                price_monthly=29000,
                currency="KRW",
                max_sites=1,
                can_publish=True,
            ),
        ]


def test_list_plans_does_not_require_authentication() -> None:
    app.dependency_overrides[get_plan_service] = lambda: FakePlanService()

    try:
        client = TestClient(app)
        response = client.get("/api/v1/plans")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert body["items"][0]["code"] == "FREE"
    assert body["items"][0]["can_publish"] is False
    assert body["items"][1]["code"] == "PRO"
    assert body["items"][2]["code"] == "MAX"


def test_plan_service_returns_active_plan_list_response() -> None:
    async def run_list_plans() -> None:
        plan_service = PlanService(session=None)
        plan_service.plan_repository = FakePlanRepository()

        response = await plan_service.list_active_plans()

        assert len(response.items) == 2
        assert response.items[0].code == "FREE"
        assert response.items[0].price_monthly == 0
        assert response.items[1].code == "PRO"
        assert response.items[1].can_publish is True

    asyncio.run(run_list_plans())
