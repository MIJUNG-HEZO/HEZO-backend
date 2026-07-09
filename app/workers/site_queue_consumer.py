"""SQS 사이트 생성 큐 컨슈머 — 별도 ECS 서비스로 실행:

    python -m app.workers.site_queue_consumer

같은 hezo-backend Docker 이미지를 다른 커맨드로 띄운다(신규 이미지
빌드 불필요). SQS_SITE_QUEUE_URL 미설정 시 즉시 종료한다.
"""

import asyncio
import json
import logging
import os
import signal
from types import FrameType
from uuid import UUID

import pybreaker
from botocore.exceptions import BotoCoreError, ClientError

from app.core.circuit_breakers import aurora_site_insert_breaker
from app.core.enums import ModuleKey, SiteType
from app.db.session import AsyncSessionLocal
from app.repositories.site_repository import SiteRepository

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_AWS_REGION = os.environ.get("AWS_REGION", "ap-northeast-2")
_SQS_SITE_QUEUE_URL = os.environ.get("SQS_SITE_QUEUE_URL", "")
_POLL_WAIT_SECONDS = 20  # SQS 롱폴링 최대값

_running = True


def _handle_shutdown(signum: int, frame: FrameType | None) -> None:
    global _running
    logger.info("종료 시그널 수신(%s), 폴링 루프 종료 예정", signum)
    _running = False


async def _create_site_from_message(body: dict) -> None:
    async def _insert() -> None:
        async with AsyncSessionLocal() as session:
            repository = SiteRepository(session)
            await repository.create(
                id=UUID(body["site_id"]),
                owner_id=UUID(body["owner_id"]),
                name=body["name"],
                site_type=SiteType(body["site_type"]),
                module_key=ModuleKey(body["module_key"]),
            )
            await session.commit()

    await aurora_site_insert_breaker.call_async(_insert)


async def run() -> None:
    if not _SQS_SITE_QUEUE_URL:
        logger.error("SQS_SITE_QUEUE_URL 미설정 — 컨슈머 종료")
        return

    import boto3

    client = boto3.client("sqs", region_name=_AWS_REGION)
    logger.info("사이트 생성 큐 컨슈머 시작: %s", _SQS_SITE_QUEUE_URL)

    while _running:
        try:
            resp = await asyncio.to_thread(
                client.receive_message,
                QueueUrl=_SQS_SITE_QUEUE_URL,
                MaxNumberOfMessages=10,
                WaitTimeSeconds=_POLL_WAIT_SECONDS,
            )
        except (BotoCoreError, ClientError) as exc:
            logger.warning("SQS 수신 실패, 5초 후 재시도: %s", exc)
            await asyncio.sleep(5)
            continue

        for message in resp.get("Messages", []):
            body = json.loads(message["Body"])
            site_id = body.get("site_id")
            try:
                await _create_site_from_message(body)
            except pybreaker.CircuitBreakerError:
                logger.warning(
                    "Aurora 서킷 open — 메시지 삭제 안 함(재시도 대기): site_id=%s", site_id
                )
                continue
            except (BotoCoreError, ClientError) as exc:
                logger.warning(
                    "사이트 insert 실패 — 메시지 삭제 안 함(재시도 대기): site_id=%s %s",
                    site_id,
                    exc,
                )
                continue

            await asyncio.to_thread(
                client.delete_message,
                QueueUrl=_SQS_SITE_QUEUE_URL,
                ReceiptHandle=message["ReceiptHandle"],
            )
            logger.info("사이트 생성 완료: site_id=%s", site_id)


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, _handle_shutdown)
    signal.signal(signal.SIGINT, _handle_shutdown)
    asyncio.run(run())
