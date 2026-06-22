import logging
import os
from typing import Annotated

import boto3
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_db_session, require_admin
from app.repositories.user_repository import UserRepository
from app.schemas.admin import (
    AdminMetricsPlaceholder,
    AdminPipelineItem,
    AdminPipelineListResponse,
    AdminUserItem,
    AdminUserListResponse,
)

logger = logging.getLogger(__name__)

_AWS_REGION = os.environ.get("AWS_DEFAULT_REGION", "ap-northeast-2")
_PIPELINE_TABLE = "hezo_pipeline_state"

router = APIRouter(prefix="/admin", tags=["Admin"])


def _scan_pipeline_table() -> list[dict]:
    try:
        ddb = boto3.client("dynamodb", region_name=_AWS_REGION)
        resp = ddb.scan(TableName=_PIPELINE_TABLE)
        return resp.get("Items", [])
    except (BotoCoreError, ClientError) as e:
        logger.warning("DynamoDB scan 실패: %s", e)
        return []


def _parse_pipeline_item(item: dict) -> AdminPipelineItem:
    def s(key: str) -> str | None:
        return item.get(key, {}).get("S")

    def n(key: str) -> int | None:
        raw = item.get(key, {}).get("N")
        return int(raw) if raw is not None else None

    return AdminPipelineItem(
        site_id=s("site_id") or "",
        publish_status=s("publish_status") or "unknown",
        attempt=n("attempt"),
        updated_at=s("updated_at"),
        error_message=s("error_message"),
    )


@router.get("/pipeline", response_model=AdminPipelineListResponse)
async def list_pipeline_states(
    _: Annotated[CurrentUser, Depends(require_admin)],
) -> AdminPipelineListResponse:
    """전체 사이트 파이프라인 상태 목록 (DynamoDB scan)."""
    raw = _scan_pipeline_table()
    items = [_parse_pipeline_item(i) for i in raw]
    return AdminPipelineListResponse(items=items, total=len(items))


@router.get("/pipeline/{site_id}", response_model=AdminPipelineItem)
async def get_pipeline_state(
    site_id: str,
    _: Annotated[CurrentUser, Depends(require_admin)],
) -> AdminPipelineItem:
    """특정 사이트 파이프라인 상태 조회."""
    try:
        ddb = boto3.client("dynamodb", region_name=_AWS_REGION)
        resp = ddb.get_item(
            TableName=_PIPELINE_TABLE,
            Key={"site_id": {"S": site_id}},
        )
        item = resp.get("Item")
        if not item:
            return AdminPipelineItem(site_id=site_id, publish_status="not_found")
        return _parse_pipeline_item(item)
    except (BotoCoreError, ClientError) as e:
        logger.warning("DynamoDB get_item 실패: %s", e)
        return AdminPipelineItem(site_id=site_id, publish_status="error")


@router.get("/users", response_model=AdminUserListResponse)
async def list_users(
    _: Annotated[CurrentUser, Depends(require_admin)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AdminUserListResponse:
    """전체 사용자 목록."""
    users = await UserRepository(session).list_all()
    items = [
        AdminUserItem(
            id=str(u.id),
            email=u.email,
            name=u.name,
            role=u.role,
            email_verified=u.email_verified_at is not None,
            created_at=u.created_at.isoformat(),
        )
        for u in users
        if u.deleted_at is None
    ]
    return AdminUserListResponse(items=items, total=len(items))


@router.get("/metrics", response_model=AdminMetricsPlaceholder)
async def get_metrics_placeholder(
    _: Annotated[CurrentUser, Depends(require_admin)],
) -> AdminMetricsPlaceholder:
    """CloudWatch 메트릭 placeholder — P5 스펙 확정 후 실제 구현."""
    return AdminMetricsPlaceholder()
