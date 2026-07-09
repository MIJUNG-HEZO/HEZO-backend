from uuid import uuid4

import pytest

from app.core.site_queue_tracker import FakeSiteQueueTracker


@pytest.mark.asyncio
async def test_fake_tracker_records_queued_status_with_owner() -> None:
    tracker = FakeSiteQueueTracker()
    site_id = uuid4()
    owner_id = uuid4()

    await tracker.mark_queued(site_id=site_id, owner_id=owner_id)
    record = await tracker.get_record(site_id=site_id)

    assert record == {"status": "queued", "owner_id": owner_id}


@pytest.mark.asyncio
async def test_fake_tracker_returns_none_for_unknown_site() -> None:
    tracker = FakeSiteQueueTracker()

    record = await tracker.get_record(site_id=uuid4())

    assert record is None
