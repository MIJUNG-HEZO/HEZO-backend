"""사이트 생성 큐잉 상태를 DynamoDB에 기록/조회.

기록 실패는 non-blocking(경고 로그만) — 이 기록은 폴링 UX 개선용일
뿐 정합성에 영향을 주지 않는다(Aurora가 최종 소스오브트루스).
owner_id를 함께 저장해 조회 시 소유권 검증에 쓴다(다른 사용자의
큐잉 상태를 site_id 추측만으로 알아낼 수 없도록).

레코드에는 TTL 속성(`ttl`, 24시간 후 만료)을 함께 쓴다 — 컨슈머가
이 레코드를 정리하지 않으므로, TTL 없이는 소프트삭제된 사이트가
Aurora에서 사라진 뒤에도 이 레코드만 남아 GET /sites/{id}가 영구히
"queued"를 반환하는 좀비 상태가 생길 수 있다. DynamoDB 테이블에
`ttl` 속성 기준 TTL이 활성화되어 있어야 실제로 만료된다(인프라
프로비저닝은 Plan 3-C/3-D 범위 — 이 모듈은 값만 써둔다).
"""

import asyncio
import logging
import os
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID

from botocore.exceptions import BotoCoreError, ClientError

logger = logging.getLogger(__name__)

_AWS_REGION = os.environ.get("AWS_REGION", "ap-northeast-2")
_SITE_QUEUE_TABLE = os.environ.get("SITE_QUEUE_TABLE", "hezo_site_queue_state")
_RECORD_TTL = timedelta(hours=24)


class SiteQueueTracker(Protocol):
    async def mark_queued(self, *, site_id: UUID, owner_id: UUID) -> None: ...
    async def get_record(self, *, site_id: UUID) -> dict | None: ...
    async def delete_record(self, *, site_id: UUID) -> None: ...


class DynamoSiteQueueTracker:
    async def mark_queued(self, *, site_id: UUID, owner_id: UUID) -> None:
        import pybreaker

        from app.core.circuit_breakers import call_breaker_async, dynamodb_site_queue_breaker

        def _put_sync() -> None:
            import boto3

            client = boto3.client("dynamodb", region_name=_AWS_REGION)
            now = datetime.now(UTC)
            client.put_item(
                TableName=_SITE_QUEUE_TABLE,
                Item={
                    "site_id": {"S": str(site_id)},
                    "owner_id": {"S": str(owner_id)},
                    "status": {"S": "queued"},
                    "created_at": {"S": now.isoformat()},
                    "ttl": {"N": str(int((now + _RECORD_TTL).timestamp()))},
                },
            )

        try:
            await call_breaker_async(dynamodb_site_queue_breaker, asyncio.to_thread(_put_sync))
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

    async def delete_record(self, *, site_id: UUID) -> None:
        """컨슈머가 Aurora insert에 성공한 직후 호출 — 레코드를 즉시 정리해
        TTL(24시간) 만료를 기다리지 않고 좀비 상태 창을 없앤다. 실패해도
        non-blocking(TTL이 최종 안전망 역할을 한다)."""

        def _delete_sync() -> None:
            import boto3

            client = boto3.client("dynamodb", region_name=_AWS_REGION)
            client.delete_item(
                TableName=_SITE_QUEUE_TABLE,
                Key={"site_id": {"S": str(site_id)}},
            )

        try:
            await asyncio.to_thread(_delete_sync)
        except (BotoCoreError, ClientError) as exc:
            logger.warning(
                "DynamoDB 큐 상태 레코드 정리 실패(non-blocking, TTL로 만료됨): site_id=%s %s",
                site_id,
                exc,
            )


class FakeSiteQueueTracker:
    def __init__(self) -> None:
        self.records: dict[UUID, dict] = {}

    async def mark_queued(self, *, site_id: UUID, owner_id: UUID) -> None:
        self.records[site_id] = {"status": "queued", "owner_id": owner_id}

    async def get_record(self, *, site_id: UUID) -> dict | None:
        return self.records.get(site_id)

    async def delete_record(self, *, site_id: UUID) -> None:
        self.records.pop(site_id, None)
