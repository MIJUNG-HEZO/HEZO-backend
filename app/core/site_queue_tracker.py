"""사이트 생성 큐잉 상태를 DynamoDB에 기록/조회.

기록 실패는 non-blocking(경고 로그만) — 이 기록은 폴링 UX 개선용일
뿐 정합성에 영향을 주지 않는다(Aurora가 최종 소스오브트루스).
owner_id를 함께 저장해 조회 시 소유권 검증에 쓴다(다른 사용자의
큐잉 상태를 site_id 추측만으로 알아낼 수 없도록).
"""

import asyncio
import logging
import os
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger(__name__)

_AWS_REGION = os.environ.get("AWS_REGION", "ap-northeast-2")
_SITE_QUEUE_TABLE = os.environ.get("SITE_QUEUE_TABLE", "hezo_site_queue_state")


class SiteQueueTracker(Protocol):
    async def mark_queued(self, *, site_id: UUID, owner_id: UUID) -> None: ...
    async def get_record(self, *, site_id: UUID) -> dict | None: ...


class DynamoSiteQueueTracker:
    async def mark_queued(self, *, site_id: UUID, owner_id: UUID) -> None:
        from app.core.circuit_breakers import dynamodb_site_queue_breaker
        import pybreaker

        def _put_sync() -> None:
            import boto3

            client = boto3.client("dynamodb", region_name=_AWS_REGION)
            client.put_item(
                TableName=_SITE_QUEUE_TABLE,
                Item={
                    "site_id": {"S": str(site_id)},
                    "owner_id": {"S": str(owner_id)},
                    "status": {"S": "queued"},
                    "created_at": {"S": datetime.now(UTC).isoformat()},
                },
            )

        try:
            await dynamodb_site_queue_breaker.call_async(asyncio.to_thread, _put_sync)
        except (BotoCoreError, ClientError, pybreaker.CircuitBreakerError) as exc:
            logger.warning(
                "DynamoDB 큐 상태 기록 실패(non-blocking, 정합성엔 영향 없음): site_id=%s %s",
                site_id,
                exc,
            )

    async def get_record(self, *, site_id: UUID) -> dict | None:
        def _get_sync() -> dict | None:
            import boto3

            client = boto3.client("dynamodb", region_name=_AWS_REGION)
            resp = client.get_item(
                TableName=_SITE_QUEUE_TABLE,
                Key={"site_id": {"S": str(site_id)}},
            )
            item = resp.get("Item")
            if not item:
                return None
            return {
                "status": item.get("status", {}).get("S"),
                "owner_id": UUID(item["owner_id"]["S"]),
            }

        try:
            return await asyncio.to_thread(_get_sync)
        except (BotoCoreError, ClientError) as exc:
            logger.warning("DynamoDB 큐 상태 조회 실패: site_id=%s %s", site_id, exc)
            return None


class FakeSiteQueueTracker:
    def __init__(self) -> None:
        self.records: dict[UUID, dict] = {}

    async def mark_queued(self, *, site_id: UUID, owner_id: UUID) -> None:
        self.records[site_id] = {"status": "queued", "owner_id": owner_id}

    async def get_record(self, *, site_id: UUID) -> dict | None:
        return self.records.get(site_id)
