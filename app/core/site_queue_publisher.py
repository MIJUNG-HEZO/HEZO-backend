"""사이트 생성 요청을 SQS에 발행하는 발행자.

SQS_SITE_QUEUE_URL 환경변수가 비어있으면(로컬 개발) publish()가
항상 False를 반환해 호출자가 즉시 동기 폴백 경로를 타도록 한다.
"""

import asyncio
import json
import logging
import os
from typing import Protocol
from uuid import UUID

import pybreaker
from botocore.exceptions import BotoCoreError, ClientError

from app.core.circuit_breakers import call_breaker_async, sqs_publish_breaker

logger = logging.getLogger(__name__)

_AWS_REGION = os.environ.get("AWS_REGION", "ap-northeast-2")
_SQS_SITE_QUEUE_URL = os.environ.get("SQS_SITE_QUEUE_URL", "")


class SiteQueuePublisher(Protocol):
    async def publish(
        self,
        *,
        site_id: UUID,
        owner_id: UUID,
        name: str,
        site_type: str,
        module_key: str,
    ) -> bool: ...


class SqsSiteQueuePublisher:
    async def publish(
        self,
        *,
        site_id: UUID,
        owner_id: UUID,
        name: str,
        site_type: str,
        module_key: str,
    ) -> bool:
        if not _SQS_SITE_QUEUE_URL:
            return False

        def _send_sync() -> None:
            import boto3

            client = boto3.client("sqs", region_name=_AWS_REGION)
            body = json.dumps(
                {
                    "site_id": str(site_id),
                    "owner_id": str(owner_id),
                    "name": name,
                    "site_type": site_type,
                    "module_key": module_key,
                }
            )
            client.send_message(QueueUrl=_SQS_SITE_QUEUE_URL, MessageBody=body)

        try:
            await call_breaker_async(sqs_publish_breaker, asyncio.to_thread(_send_sync))
            return True
        except (BotoCoreError, ClientError) as exc:
            logger.warning("SQS 발행 실패, 동기 폴백 경로로 전환: site_id=%s %s", site_id, exc)
            return False
        except pybreaker.CircuitBreakerError:
            logger.warning("SQS 서킷 open, 동기 폴백 경로로 전환: site_id=%s", site_id)
            return False


class FakeSiteQueuePublisher:
    def __init__(self, *, should_succeed: bool = True) -> None:
        self.should_succeed = should_succeed
        self.published: list[dict] = []

    async def publish(
        self,
        *,
        site_id: UUID,
        owner_id: UUID,
        name: str,
        site_type: str,
        module_key: str,
    ) -> bool:
        self.published.append(
            {
                "site_id": site_id,
                "owner_id": owner_id,
                "name": name,
                "site_type": site_type,
                "module_key": module_key,
            }
        )
        return self.should_succeed
