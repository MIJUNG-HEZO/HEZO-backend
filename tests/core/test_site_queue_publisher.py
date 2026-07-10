from uuid import uuid4

import pytest

from app.core.site_queue_publisher import FakeSiteQueuePublisher, SqsSiteQueuePublisher


@pytest.mark.asyncio
async def test_fake_publisher_records_published_message() -> None:
    publisher = FakeSiteQueuePublisher(should_succeed=True)
    site_id = uuid4()
    owner_id = uuid4()

    result = await publisher.publish(
        site_id=site_id,
        owner_id=owner_id,
        name="강남 한의원",
        site_type="landing",
        module_key="medical",
    )

    assert result is True
    assert publisher.published == [
        {
            "site_id": site_id,
            "owner_id": owner_id,
            "name": "강남 한의원",
            "site_type": "landing",
            "module_key": "medical",
        }
    ]


@pytest.mark.asyncio
async def test_fake_publisher_can_simulate_failure() -> None:
    publisher = FakeSiteQueuePublisher(should_succeed=False)

    result = await publisher.publish(
        site_id=uuid4(), owner_id=uuid4(), name="x", site_type="landing", module_key="medical",
    )

    assert result is False


@pytest.mark.asyncio
async def test_sqs_publisher_returns_false_when_queue_url_not_configured(monkeypatch) -> None:
    monkeypatch.setattr("app.core.site_queue_publisher._SQS_SITE_QUEUE_URL", "")
    publisher = SqsSiteQueuePublisher()

    result = await publisher.publish(
        site_id=uuid4(), owner_id=uuid4(), name="x", site_type="landing", module_key="medical",
    )

    assert result is False
