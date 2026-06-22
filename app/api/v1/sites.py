import asyncio
import concurrent.futures
import json
import logging
import os
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

import boto3
import httpx
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.api.deps import (
    CurrentUser,
    get_site_service,
    require_authenticated,
    require_email_verified,
)
from app.core.config import settings
from app.schemas.chat import ChatRequest, ChatResponse
from app.schemas.site import (
    SiteCreateRequest,
    SiteListResponse,
    SitePublishAvailabilityResponse,
    SiteResponse,
    SiteUpdateRequest,
)
from app.services.site_service import SiteService

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# AWS 설정 — 환경변수 없으면 로컬 모드(Step Functions 미호출)
# ---------------------------------------------------------------------------
_AWS_REGION = os.environ.get("AWS_REGION", "ap-northeast-2")
_STEP_FUNCTIONS_ARN = os.environ.get("STEP_FUNCTIONS_ARN", "")         # hezo_pipeline 상태머신 ARN
_ARTIFACTS_BUCKET = os.environ.get("ARTIFACTS_BUCKET", "hezo-artifacts")
_AWS_ENABLED = bool(_STEP_FUNCTIONS_ARN)                                # ARN 있으면 AWS 모드


def _get_sfn_client():
    return boto3.client("stepfunctions", region_name=_AWS_REGION)


def _get_s3_client():
    return boto3.client("s3", region_name=_AWS_REGION)


def _start_pipeline(site_id: str, contract_json: dict) -> dict:
    """
    Step Functions 파이프라인 실행 시작.
    returns: { execution_arn, status }
    raises: RuntimeError (AWS 호출 실패 시)
    """
    sfn = _get_sfn_client()
    execution_name = f"site-{site_id[:8]}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    input_payload = json.dumps(
        {"site_id": site_id, "contract_json": contract_json},
        ensure_ascii=False,
    )
    resp = sfn.start_execution(
        stateMachineArn=_STEP_FUNCTIONS_ARN,
        name=execution_name,
        input=input_payload,
    )
    return {
        "execution_arn": resp["executionArn"],
        "status": "running",
        "started_at": resp["startDate"].isoformat(),
    }


def _get_pipeline_status(site_id: str) -> dict:
    """
    DynamoDB hezo_pipeline_state에서 site_id의 파이프라인 상태를 조회.
    DynamoDB 없으면 Step Functions 최신 실행 상태를 직접 조회.
    """
    # DynamoDB 우선 조회
    try:
        ddb = boto3.client("dynamodb", region_name=_AWS_REGION)
        resp = ddb.get_item(
            TableName="hezo_pipeline_state",
            Key={"site_id": {"S": site_id}},
        )
        item = resp.get("Item")
        if item:
            return {
                "site_id": site_id,
                "pipeline_status": item.get("pipeline_status", {}).get("S", "unknown"),
                "render_spec_s3_key": item.get("render_spec_s3_key", {}).get("S"),
                "updated_at": item.get("updated_at", {}).get("S"),
                "error": item.get("error_message", {}).get("S"),
            }
    except (BotoCoreError, ClientError) as e:
        logger.warning("DynamoDB 조회 실패, Step Functions fallback: %s", e)

    # Step Functions 최신 실행 목록에서 조회 (fallback)
    try:
        sfn = _get_sfn_client()
        resp = sfn.list_executions(
            stateMachineArn=_STEP_FUNCTIONS_ARN,
            statusFilter="RUNNING",
            maxResults=10,
        )
        for ex in resp.get("executions", []):
            if site_id in ex.get("name", ""):
                return {
                    "site_id": site_id,
                    "pipeline_status": "running",
                    "execution_arn": ex["executionArn"],
                    "updated_at": ex["startDate"].isoformat(),
                }
    except (BotoCoreError, ClientError) as e:
        logger.warning("Step Functions 조회 실패: %s", e)

    return {"site_id": site_id, "pipeline_status": "unknown"}

router = APIRouter(prefix="/sites", tags=["Sites"])

# ---------------------------------------------------------------------------
# 온보딩 데이터 인메모리 스토어 (로컬 개발용 — 재시작 시 초기화)
# 추후: Site 모델에 onboarding_data JSONB 컬럼 추가 후 DB에서 관리
# ---------------------------------------------------------------------------
_site_onboarding: dict[str, dict] = {}


class _BusinessPayload(BaseModel):
    business_name: str = ""


class _ServicesPayload(BaseModel):
    services: list[str] = []


class _ContactPayload(BaseModel):
    phone: str = ""
    email: str = ""
    address: str = ""
    hours: str = ""


class _StructurePayload(BaseModel):
    structure: str = ""
    template_id: str = ""


def _build_contract(site_id: str) -> dict:
    """
    온보딩 데이터에서 G slot-based Contract JSON (schema_version: 0.1.0) 생성.
    생성 에이전트(Bedrock)가 소비하는 확정 포맷.
    """
    overrides = _site_onboarding.get(site_id, {})

    # ── 슬롯 값 추출 ──────────────────────────────────────────────────────────
    business_name   = overrides.get("business_name", "")
    services        = overrides.get("services", [])
    contact         = overrides.get("contact", {})
    phone           = contact.get("phone", "")
    email           = contact.get("email", "")
    address         = contact.get("address", "")
    template_id     = overrides.get("template_id", "landing_general")
    category        = overrides.get("structure", "landing")

    # 템플릿 slug: "landing_tax" → "tax", "01-clinic-landing" → "clinic"
    slug_raw        = template_id.replace("landing_", "").replace("-landing", "")
    slug            = slug_raw.split("-")[0] if "-" in slug_raw else slug_raw

    # 필수 슬롯 채움 여부 판단 — generation_ready 기준
    filled          = bool(business_name and services and phone)
    slot_score      = round(
        (bool(business_name) * 0.3)
        + (bool(services) * 0.3)
        + (bool(phone) * 0.2)
        + (bool(address) * 0.1)
        + (bool(email) * 0.1),
        2,
    )

    return {
        "schema_version": "0.1.0",
        "ids": {
            "project_id": f"project_{site_id[:8]}",
            "site_id": site_id,
            "tenant_id": "tenant_hezo_app",
        },
        "template": {
            "category": category,
            "template_id": template_id,
            "slug": slug,
        },
        "slots": {
            "business_name":    business_name,
            "industry":         "general",
            "business_type":    category,
            "business_region":  address or "한국",
            "site_goal":        "lead_capture",
            "target_audience":  ["잠재 고객"],
            "core_services":    services,
            "pain_points":      [],
            "required_sections":["hero", "services", "faq", "contact_form", "footer"],
            "tone_style":       ["professional", "trustworthy"],
            "brand_keywords":   [business_name] if business_name else ["전문 서비스"],
            "cta":              ["지금 상담 신청", "카카오톡 상담"],
            "contact_method":   (
                ["phone", "email", "contact_form"]
                if email
                else ["phone", "contact_form"]
            ),
            "phone":            phone,
            "kakao_channel":    "",
            "business_hours":   "평일 09:00-18:00",
            "business_number":  None,
            "reference_site_exists": False,
            "reference_sites":  [],
        },
        "slot_status": {
            "business_name":    {"status": "filled" if business_name else "missing", "confidence": 1.0 if business_name else 0, "source": "user", "ask_count": 1},
            "core_services":    {"status": "filled" if services else "missing",      "confidence": 0.9 if services else 0,       "source": "user", "ask_count": 1},
            "phone":            {"status": "filled" if phone else "missing",          "confidence": 1.0 if phone else 0,          "source": "user", "ask_count": 1},
            "business_number":  {"status": "missing", "confidence": 0, "source": None, "ask_count": 0},
        },
        "evidence": {
            "wiki_refs":      [],
            "research_refs":  [],
        },
        "gates": {
            "completeness_score": slot_score,
            "preview_ready":      True,
            "generation_ready":   filled,
            "missing_items": (
                []
                if filled
                else [
                    {"slot_key": k, "reason": f"{k} 필드가 누락되었습니다."}
                    for k in (
                        (["business_name"] if not business_name else [])
                        + (["core_services"] if not services else [])
                        + (["phone"] if not phone else [])
                    )
                ]
            ),
            "unresolved_items": [],
        },
    }



@router.get("", response_model=SiteListResponse)
async def list_sites(
    current_user: Annotated[CurrentUser, Depends(require_authenticated)],
    site_service: Annotated[SiteService, Depends(get_site_service)],
) -> SiteListResponse:
    return await site_service.list_sites(user_id=current_user.id)


@router.get("/{site_id}/publish-availability", response_model=SitePublishAvailabilityResponse)
async def check_publish_availability(
    site_id: UUID,
    current_user: Annotated[CurrentUser, Depends(require_authenticated)],
    site_service: Annotated[SiteService, Depends(get_site_service)],
) -> SitePublishAvailabilityResponse:
    return await site_service.check_publish_availability(
        user_id=current_user.id,
        site_id=site_id,
    )


@router.get("/{site_id}/contract")
async def get_site_contract(
    site_id: UUID,
    current_user: Annotated[CurrentUser, Depends(require_authenticated)],
) -> dict:
    """Contract JSON 조회 — 온보딩 입력값을 mock에 덮어씌워 반환."""
    return _build_contract(str(site_id))


@router.get("/{site_id}", response_model=SiteResponse)
async def get_site(
    site_id: UUID,
    current_user: Annotated[CurrentUser, Depends(require_authenticated)],
    site_service: Annotated[SiteService, Depends(get_site_service)],
) -> SiteResponse:
    return await site_service.get_site(user_id=current_user.id, site_id=site_id)


@router.patch("/{site_id}", response_model=SiteResponse)
async def update_site(
    site_id: UUID,
    payload: SiteUpdateRequest,
    current_user: Annotated[CurrentUser, Depends(require_authenticated)],
    site_service: Annotated[SiteService, Depends(get_site_service)],
) -> SiteResponse:
    return await site_service.update_site(
        user_id=current_user.id,
        site_id=site_id,
        payload=payload,
    )


@router.delete("/{site_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_site(
    site_id: UUID,
    current_user: Annotated[CurrentUser, Depends(require_authenticated)],
    site_service: Annotated[SiteService, Depends(get_site_service)],
) -> None:
    await site_service.delete_site(user_id=current_user.id, site_id=site_id)


# ---------------------------------------------------------------------------
# 온보딩 스텁 엔드포인트 — 챗봇 대화 단계별 호출
# 추후: 각 핸들러에 실제 Contract JSON 필드 업데이트 로직 추가
# ---------------------------------------------------------------------------

@router.patch("/{site_id}/onboarding/business", status_code=status.HTTP_204_NO_CONTENT)
async def update_onboarding_business(
    site_id: UUID,
    payload: _BusinessPayload,
    current_user: Annotated[CurrentUser, Depends(require_authenticated)],
) -> None:
    if payload.business_name:
        _site_onboarding.setdefault(str(site_id), {})["business_name"] = payload.business_name


@router.patch("/{site_id}/onboarding/industry", status_code=status.HTTP_204_NO_CONTENT)
async def update_onboarding_industry(
    site_id: UUID,
    current_user: Annotated[CurrentUser, Depends(require_authenticated)],
) -> None:
    return None


@router.patch("/{site_id}/onboarding/structure", status_code=status.HTTP_204_NO_CONTENT)
async def update_onboarding_structure(
    site_id: UUID,
    payload: _StructurePayload,
    current_user: Annotated[CurrentUser, Depends(require_authenticated)],
) -> None:
    store = _site_onboarding.setdefault(str(site_id), {})
    if payload.structure:
        store["structure"] = payload.structure
    if payload.template_id:
        store["template_id"] = payload.template_id


@router.patch("/{site_id}/onboarding/services", status_code=status.HTTP_204_NO_CONTENT)
async def update_onboarding_services(
    site_id: UUID,
    payload: _ServicesPayload,
    current_user: Annotated[CurrentUser, Depends(require_authenticated)],
) -> None:
    if payload.services:
        _site_onboarding.setdefault(str(site_id), {})["services"] = payload.services


@router.patch("/{site_id}/onboarding/customers", status_code=status.HTTP_204_NO_CONTENT)
async def update_onboarding_customers(
    site_id: UUID,
    current_user: Annotated[CurrentUser, Depends(require_authenticated)],
) -> None:
    return None


@router.patch("/{site_id}/onboarding/contact", status_code=status.HTTP_204_NO_CONTENT)
async def update_onboarding_contact(
    site_id: UUID,
    payload: _ContactPayload,
    current_user: Annotated[CurrentUser, Depends(require_authenticated)],
) -> None:
    _site_onboarding.setdefault(str(site_id), {})["contact"] = {
        "phone": payload.phone,
        "email": payload.email,
        "address": payload.address,
    }


@router.patch("/{site_id}/onboarding/legal", status_code=status.HTTP_204_NO_CONTENT)
async def update_onboarding_legal(
    site_id: UUID,
    current_user: Annotated[CurrentUser, Depends(require_authenticated)],
) -> None:
    return None


@router.patch("/{site_id}/onboarding/additional", status_code=status.HTTP_204_NO_CONTENT)
async def update_onboarding_additional(
    site_id: UUID,
    current_user: Annotated[CurrentUser, Depends(require_authenticated)],
) -> None:
    return None


@router.post("/{site_id}/onboarding/complete", status_code=status.HTTP_204_NO_CONTENT)
async def complete_onboarding(
    site_id: UUID,
    current_user: Annotated[CurrentUser, Depends(require_authenticated)],
) -> None:
    return None


# ---------------------------------------------------------------------------
# Contract / Preview 스텁 — 추후 생성 에이전트 트리거로 교체
# ---------------------------------------------------------------------------

@router.post("/{site_id}/contract", status_code=status.HTTP_204_NO_CONTENT)
async def create_contract(
    site_id: UUID,
    current_user: Annotated[CurrentUser, Depends(require_authenticated)],
) -> None:
    return None


class _PreviewResponse(BaseModel):
    site_id: str
    preview_mode: str  # "triggered" | "mock"
    preview_url: str | None = None
    message: str


@router.post("/{site_id}/preview", response_model=_PreviewResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_preview(
    site_id: UUID,
    current_user: Annotated[CurrentUser, Depends(require_authenticated)],
) -> _PreviewResponse:
    """
    P3 빌드 워커 preview 모드 트리거.
    - P3_BUILD_ENDPOINT 설정됨: P3 HTTP 서비스에 비동기 트리거
    - P3_BUILD_ENDPOINT 미설정: mock 202 반환 (로컬 개발용)
    """
    sid = str(site_id)
    endpoint = settings.p3_build_endpoint
    if not endpoint:
        return _PreviewResponse(
            site_id=sid,
            preview_mode="mock",
            message="P3_BUILD_ENDPOINT 미설정 — 로컬 개발 모드입니다.",
        )

    contract = _build_contract(sid)
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{endpoint.rstrip('/')}/invocations",
                json={"site_id": sid, "mode": "preview", "contract": contract},
            )
            resp.raise_for_status()
            data = resp.json()
    except (httpx.HTTPStatusError, httpx.RequestError) as e:
        logger.error("P3 preview 트리거 실패 site=%s: %s", sid, e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="프리뷰 생성 서비스에 연결할 수 없습니다.",
        ) from e

    return _PreviewResponse(
        site_id=sid,
        preview_mode="triggered",
        preview_url=data.get("preview_url"),
        message="프리뷰 생성이 시작되었습니다.",
    )


@router.post("/{site_id}/preview/retry-image", status_code=status.HTTP_204_NO_CONTENT)
async def retry_preview_image(
    site_id: UUID,
    current_user: Annotated[CurrentUser, Depends(require_authenticated)],
) -> None:
    return None


@router.post("/{site_id}/preview/retry-content", status_code=status.HTTP_204_NO_CONTENT)
async def retry_preview_content(
    site_id: UUID,
    current_user: Annotated[CurrentUser, Depends(require_authenticated)],
) -> None:
    return None


class _PipelineStatusResponse(BaseModel):
    site_id: str
    pipeline_status: str          # "running" | "generation_complete" | "generation_failed" | "published" | "unknown"
    render_spec_s3_key: str | None = None
    execution_arn: str | None = None
    updated_at: str | None = None
    error: str | None = None


class _PublishResponse(BaseModel):
    site_id: str
    mode: str                     # "aws_pipeline" | "local"
    pipeline_status: str
    execution_arn: str | None = None
    message: str


@router.post("/{site_id}/publish", response_model=_PublishResponse)
async def publish_site(
    site_id: UUID,
    current_user: Annotated[CurrentUser, Depends(require_email_verified)],
    site_service: Annotated[SiteService, Depends(get_site_service)],
) -> _PublishResponse:
    """
    발행 버튼 → Step Functions 파이프라인 시작.
    - AWS 모드 (STEP_FUNCTIONS_ARN 설정됨): contract JSON을 S3에 업로드 후 파이프라인 실행
    - 로컬 모드 (ARN 없음): 기존 site_service.publish_site() 호출 (즉시 완료)
    """
    sid = str(site_id)

    # 구독 플랜 검증 (기존 서비스 로직 재사용)
    try:
        await site_service.check_publish_availability(
            user_id=current_user.id, site_id=site_id
        )
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e

    if _AWS_ENABLED:
        # ── AWS 파이프라인 모드 ──────────────────────────────────────────────
        contract_json = _build_contract(sid)

        # S3에 contract_final.json 먼저 업로드 (Step Functions가 읽을 수 있도록)
        try:
            s3 = _get_s3_client()
            s3.put_object(
                Bucket=_ARTIFACTS_BUCKET,
                Key=f"sites/{sid}/contract_final.json",
                Body=json.dumps(contract_json, ensure_ascii=False).encode("utf-8"),
                ContentType="application/json",
            )
        except (BotoCoreError, ClientError) as e:
            logger.error("S3 contract 업로드 실패 site=%s: %s", sid, e)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="S3 업로드에 실패했습니다. AWS 자격증명을 확인하세요.",
            ) from e

        # Step Functions 실행 시작
        try:
            pipeline_info = _start_pipeline(sid, contract_json)
        except (BotoCoreError, ClientError) as e:
            logger.error("Step Functions 실행 실패 site=%s: %s", sid, e)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="파이프라인 실행에 실패했습니다.",
            ) from e

        return _PublishResponse(
            site_id=sid,
            mode="aws_pipeline",
            pipeline_status="running",
            execution_arn=pipeline_info.get("execution_arn"),
            message="파이프라인이 시작되었습니다. 생성 에이전트가 render_spec을 구성 중입니다.",
        )

    else:
        # ── 로컬 모드 (AWS 미설정) ───────────────────────────────────────────
        try:
            await site_service.publish_site(user_id=current_user.id, site_id=site_id)
        except Exception as e:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e)) from e

        return _PublishResponse(
            site_id=sid,
            mode="local",
            pipeline_status="published",
            message="사이트가 발행되었습니다. (로컬 모드 — Step Functions 미설정)",
        )


@router.get("/{site_id}/pipeline/status", response_model=_PipelineStatusResponse)
async def get_pipeline_status(
    site_id: UUID,
    current_user: Annotated[CurrentUser, Depends(require_authenticated)],
) -> _PipelineStatusResponse:
    """
    파이프라인 실행 상태 폴링용 엔드포인트.
    프론트엔드가 3초마다 호출하여 생성 에이전트 → 빌드 → 검증 → 배포 진행 상황 표시.
    """
    sid = str(site_id)
    if not _AWS_ENABLED:
        return _PipelineStatusResponse(
            site_id=sid,
            pipeline_status="published",
            message="로컬 모드",
        )
    result = _get_pipeline_status(sid)
    return _PipelineStatusResponse(**result)


@router.post("", response_model=SiteResponse, status_code=status.HTTP_201_CREATED)
async def create_site(
    payload: SiteCreateRequest,
    current_user: Annotated[CurrentUser, Depends(require_email_verified)],
    site_service: Annotated[SiteService, Depends(get_site_service)],
) -> SiteResponse:
    return await site_service.create_site(
        user_id=current_user.id,
        email_verified=current_user.email_verified,
        payload=payload,
    )


# ---------------------------------------------------------------------------
# P1 챗봇 프록시 — P1 AgentCore /invocations 로 중계
# ---------------------------------------------------------------------------

_P1_MOCK_MESSAGES = [
    "안녕하세요! 비즈니스 이름을 알려주세요.",
    "감사합니다. 주요 서비스나 제품을 3가지 이내로 알려주시겠어요?",
    "좋습니다. 연락처(전화번호)를 알려주세요.",
    "거의 다 됐어요. 주소를 알려주시겠어요?",
    "필요한 정보가 모두 수집됐습니다. 홈페이지 프리뷰를 생성할게요!",
]
_p1_mock_index: dict[str, int] = {}


_p1_executor: concurrent.futures.ThreadPoolExecutor | None = None


def _get_p1_executor() -> concurrent.futures.ThreadPoolExecutor:
    global _p1_executor
    if _p1_executor is None:
        _p1_executor = concurrent.futures.ThreadPoolExecutor(max_workers=4, thread_name_prefix="p1-agentcore")
    return _p1_executor


@router.post("/{site_id}/chat", response_model=ChatResponse)
async def chat_with_p1(
    site_id: UUID,
    payload: ChatRequest,
    current_user: Annotated[CurrentUser, Depends(require_authenticated)],
) -> ChatResponse:
    """
    P1 챗봇 에이전트 프록시.
    - P1_AGENTCORE_RUNTIME_ARN 설정: boto3 bedrock-agentcore 호출
    - 미설정: 순차 mock 응답 (로컬 개발용)
    """
    sid = str(site_id)
    session_key = f"{sid}:{payload.session_id}"
    runtime_arn = settings.p1_agentcore_runtime_arn

    if not runtime_arn:
        idx = _p1_mock_index.get(session_key, 0)
        msg = _P1_MOCK_MESSAGES[min(idx, len(_P1_MOCK_MESSAGES) - 1)]
        _p1_mock_index[session_key] = idx + 1
        turn_done = idx >= len(_P1_MOCK_MESSAGES) - 1
        return ChatResponse(
            session_id=payload.session_id,
            assistant_message=msg,
            turn_status="ready_for_contract_compile" if turn_done else "answer_accepted",
            next_stage="contract_compile" if turn_done else "proactive_questioning",
            current_slot="",
            mock=True,
        )

    agentcore_payload = {
        "sessionId": payload.session_id,
        "inputText": payload.user_message,
        "sessionAttributes": {
            "action": "chat_turn",
            "site_id": sid,
            "user_id": str(current_user.id),
            "answer": payload.user_message,
            "answered_slot": payload.answered_slot or "",
            "known_answers": json.dumps(payload.known_answers or {}, ensure_ascii=False),
            "domain": payload.domain or "general",
            "domain_label": payload.domain_label or "",
            "category": payload.category or "landing",
            "selected_template": payload.template_id or "",
            "storage_mode": "aws",
        },
    }

    def _invoke() -> dict:
        client = boto3.client("bedrock-agentcore", region_name="ap-northeast-2")
        resp = client.invoke_agent_runtime(
            agentRuntimeArn=runtime_arn,
            payload=json.dumps(agentcore_payload),
            contentType="application/json",
            accept="application/json",
        )
        body_key = "body" if "body" in resp else next(
            (k for k in resp if hasattr(resp[k], "read")), None
        )
        if body_key is None:
            logger.error("P1 AgentCore 응답 키 목록: %s", list(resp.keys()))
            raise ValueError(f"AgentCore 응답에서 body를 찾을 수 없음: {list(resp.keys())}")
        return json.loads(resp[body_key].read())

    try:
        loop = asyncio.get_event_loop()
        data: dict = await loop.run_in_executor(_get_p1_executor(), _invoke)
    except (BotoCoreError, ClientError) as e:
        logger.error("P1 AgentCore 오류 site=%s: %s", sid, e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="챗봇 서비스에 일시적 오류가 발생했습니다.",
        ) from e

    meta: dict = data.get("metadata", {})
    candidates: list = meta.get("question_candidates") or []
    current_slot = candidates[0].get("slot", "") if candidates else ""

    return ChatResponse(
        session_id=payload.session_id,
        assistant_message=data.get("output", ""),
        turn_status=meta.get("turn_status", "answer_accepted"),
        next_stage=meta.get("next_stage", "proactive_questioning"),
        slot_filled=meta.get("known_answers", {}),
        missing_slots=meta.get("missing_slots", []),
        current_slot=current_slot,
        mock=False,
    )
