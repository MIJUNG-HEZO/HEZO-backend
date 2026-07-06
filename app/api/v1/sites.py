import asyncio
import concurrent.futures
import json
import logging
import os
import re
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
_PIPELINE_TABLE = os.environ.get("PIPELINE_TABLE", "hezo_pipeline_state")
_AWS_ENABLED = bool(_STEP_FUNCTIONS_ARN)                                # ARN 있으면 AWS 모드


def _get_sfn_client():
    return boto3.client("stepfunctions", region_name=_AWS_REGION)


def _batch_get_domain_urls(site_ids: list[str]) -> dict[str, str]:
    """발행된 사이트 목록의 domain_url을 DynamoDB batch_get_item으로 조회."""
    return {
        sid: d["domain_url"]
        for sid, d in _batch_get_domain_urls_with_status(site_ids).items()
        if d.get("domain_url")
    }


def _batch_get_domain_urls_with_status(site_ids: list[str]) -> dict[str, dict]:
    """site_id 목록에 대해 DynamoDB에서 publish_status + domain_url 일괄 조회."""
    if not site_ids:
        return {}
    try:
        ddb = boto3.client("dynamodb", region_name=_AWS_REGION)
        keys = [{"site_id": {"S": sid}} for sid in site_ids]
        resp = ddb.batch_get_item(
            RequestItems={
                _PIPELINE_TABLE: {
                    "Keys": keys,
                    "ProjectionExpression": "site_id, domain_url, publish_status",
                }
            }
        )
        result: dict[str, dict] = {}
        for item in resp.get("Responses", {}).get(_PIPELINE_TABLE, []):
            sid = item.get("site_id", {}).get("S")
            if sid:
                result[sid] = {
                    "domain_url": item.get("domain_url", {}).get("S"),
                    "publish_status": item.get("publish_status", {}).get("S"),
                }
        return result
    except (BotoCoreError, ClientError) as e:
        logger.warning("DynamoDB batch_get_item 실패: %s", e)
        return {}


def _get_s3_client():
    return boto3.client("s3", region_name=_AWS_REGION)


def _extract_template_info(contract: dict) -> tuple[str, str]:
    """
    contract JSON에서 (template_type, template_category) 추출.
    schema 1.0.0: template.template_id="13-tax-accounting", template.template_category="landing"
    schema 0.1.0: template.slug="general", template.category="landing"
    """
    t = contract.get("template", {})
    if contract.get("schema_version") == "1.0.0":
        category = t.get("template_category", "landing")
        template_id = t.get("template_id", "")
        # "13-tax-accounting" → "tax-accounting", "10-wine-market" → "wine-market"
        parts = template_id.split("-", 1)
        if len(parts) == 2 and parts[0].isdigit() and parts[1]:
            ttype = parts[1]
        elif template_id:
            ttype = template_id
        else:
            ttype = "general"
    else:
        category = t.get("category", "landing")
        ttype = t.get("slug", "general") or "general"
    return ttype, category


def _start_pipeline(site_id: str, template_type: str, template_category: str) -> dict:
    """
    Step Functions hezo-site-pipeline 실행.
    SM 입력: { site_id, template_type, template_category }
    PublishSiteEvent 스텝이 $.template_type, $.template_category 를 EventBridge 이벤트에 포함.
    returns: { execution_arn, status, started_at }
    """
    sfn = _get_sfn_client()
    execution_name = f"s-{site_id}-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    input_payload = json.dumps(
        {
            "site_id": site_id,
            "template_type": template_type,
            "template_category": template_category,
        },
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
            TableName=_PIPELINE_TABLE,
            Key={"site_id": {"S": site_id}},
        )
        item = resp.get("Item")
        if item:
            raw_status = item.get("publish_status", {}).get("S", "unknown")
            # DynamoDB publish_status → 프론트 기대값 매핑
            status_map = {
                "building": "running",
                "validating": "running",
                "retrying": "running",
                "published": "published",
                "failed": "generation_failed",
                "rolled_back": "generation_failed",
            }
            pipeline_status = status_map.get(raw_status, raw_status)
            return {
                "site_id": site_id,
                "pipeline_status": pipeline_status,
                "domain_url": item.get("domain_url", {}).get("S"),
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
        executions = resp.get("executions", [])
        site_exec = next(
            (e for e in executions if site_id in e.get("name", "")),
            None,
        )
        if site_exec:
            sfn_status = site_exec["status"]
            status_map = {
                "RUNNING": "building",
                "SUCCEEDED": "published",
                "FAILED": "failed",
                "TIMED_OUT": "failed",
                "ABORTED": "failed",
            }
            stop_date = site_exec.get("stopDate")
            start_date = site_exec.get("startDate")
            updated = (stop_date or start_date)
            return {
                "site_id": site_id,
                "pipeline_status": status_map.get(sfn_status, "unknown"),
                "domain_url": None,
                "execution_arn": site_exec.get("executionArn"),
                "updated_at": updated.isoformat() if updated else None,
            }
    except (BotoCoreError, ClientError) as e:
        logger.warning("Step Functions 조회 실패: %s", e)

    return {"site_id": site_id, "pipeline_status": "unknown", "domain_url": None}

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


def _to_list(value: object, sep: str = ",") -> list[str]:
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    if isinstance(value, str) and value.strip():
        return [s.strip() for s in value.split(sep) if s.strip()]
    return []


def _parse_service_items(raw: str) -> list[dict]:
    """서비스 목록 파싱. "서비스명/설명, 서비스명2/설명2" 형식 지원.
    슬래시 없으면 name만 채우고 desc는 빈 문자열."""
    result = []
    for item in _to_list(raw):
        if "/" in item:
            name, desc = item.split("/", 1)
            result.append({"name": name.strip(), "desc": desc.strip()})
        else:
            result.append({"name": item, "desc": ""})
    return result


def _parse_wine_lineup(wine_lineup: str) -> list[dict]:
    """
    wine_lineup 문자열 파싱. 가격에 쉼표 포함(55,000원) 처리.
    형식: "와인명/종류/가격/설명, 와인명2/..."
    반환: [{"name": .., "type": .., "price": .., "desc": ..}, ...]
    """
    if not wine_lineup or not wine_lineup.strip():
        return []

    # 쉼표 분리 후, 숫자로 시작하는 부분은 앞 항목 가격의 연속으로 병합
    # "이탈리아 키안티/레드/55" + ",000원/스테이크 페어링" → 합침
    raw_parts = wine_lineup.split(",")
    merged: list[str] = []
    current = ""
    for part in raw_parts:
        stripped = part.lstrip()
        if current and stripped and stripped[0].isdigit():
            current = current + "," + part
        else:
            if current.strip():
                merged.append(current.strip())
            current = part
    if current.strip():
        merged.append(current.strip())

    wines: list[dict] = []
    for entry in merged:
        parts = [p.strip() for p in entry.split("/")]
        if len(parts) >= 4:
            wines.append({
                "name": parts[0],
                "type": parts[1],
                "price": parts[2],
                "desc": "/".join(parts[3:]),
            })
        elif len(parts) == 3:
            wines.append({"name": parts[0], "type": parts[1], "price": parts[2], "desc": ""})
        elif parts and parts[0]:
            wines.append({"name": parts[0], "type": "", "price": "", "desc": ""})
    return wines


_TEMPLATE_CATEGORY_MAP: dict[str, str] = {
    "01-clinic-landing": "landing", "02-course-landing": "landing",
    "03-saas-product": "landing",   "05-lifting-clinic": "landing",
    "07-legal-consulting": "landing","13-tax-accounting": "landing",
    "17-solar-energy": "landing",    "landing_general": "landing",
    "01-food-travel-blog": "blog",  "03-developer-docs": "blog",
    "05-expert-column": "blog",     "17-career-notebook": "blog",
    "01-cafe-menu": "store",        "05-booking-service": "store",
    "06-oops-nail": "store",        "10-wine-market": "store",
}


def _get_template_category(template_id: str) -> str:
    if template_id in _TEMPLATE_CATEGORY_MAP:
        return _TEMPLATE_CATEGORY_MAP[template_id]
    if "blog" in template_id:
        return "blog"
    if any(k in template_id for k in ("store", "cafe", "menu", "nail", "wine")):
        return "store"
    return "landing"


def _build_render_spec(contract: dict) -> dict:
    """Contract JSON → P3가 소비하는 simplified render_spec (프리뷰용, template-specific)."""
    slots = contract.get("slots", {})
    template = contract.get("template", {})
    template_id = template.get("template_id") or "01-clinic-landing"
    template_category = _get_template_category(template_id)

    business_name = slots.get("business_name") or "My Business"
    phone         = slots.get("phone") or ""
    kakao_channel = slots.get("kakao_channel") or ""
    business_hours = slots.get("business_hours") or "평일 09:00-18:00"

    # Template-specific 필드 추출
    service_items: list[dict] = []  # Services block용 items
    field_label = "서비스"
    hero_subheadline = ""      # hero-subheadline 주입용 (wine-market TONIGHT PICK 등)
    hero_featured_price = ""   # hero strong.price 주입용

    if "wine" in template_id:
        field_label = "와인"
        parsed_wines = _parse_wine_lineup(slots.get("wine_lineup") or "")
        featured = parsed_wines[0] if parsed_wines else {}
        h1_text = featured.get("name") or business_name
        hero_subheadline = featured.get("desc") or ""
        hero_featured_price = featured.get("price") or ""
        service_items = [
            {
                "name": w["name"],
                "desc": f"{w['type']} | {w['desc']}" if w.get("desc") else w.get("type", ""),
                "price": w["price"],
            }
            for w in parsed_wines[:4]
        ]
        main_names = [w["name"] for w in parsed_wines[:3]]
        service_text = ", ".join(main_names) if main_names else "프리미엄 와인"
        faq_items = [
            {
                "q": f"{business_name}에서 판매하는 와인은 무엇인가요?",
                "a": f"{service_text} 등 엄선된 와인을 취급합니다.",
            },
            {"q": "영업 시간이 어떻게 되나요?", "a": business_hours},
            {"q": "구매 문의는 어떻게 하나요?", "a": "전화 또는 방문으로 문의해 주세요."},
        ]

    elif "tax" in template_id:
        field_label = "서비스"
        parsed_tax = _parse_service_items(slots.get("tax_services") or "")
        h1_text = f"{slots.get('business_region', '전문')} 세무회계 서비스"
        service_names = [s["name"] for s in parsed_tax]
        service_text = ", ".join(service_names[:2]) if service_names else "세무회계 서비스"
        service_items = parsed_tax[:3]
        faq_items = [
            {"q": f"{business_name}의 서비스가 무엇인가요?",
             "a": f"{service_text}를 제공합니다."},
            {"q": "영업 시간이 어떻게 되나요?", "a": business_hours},
            {"q": "상담은 어떻게 신청하나요?", "a": "전화 또는 카카오톡으로 문의해 주세요."},
        ]

    elif "career" in template_id:
        field_label = "경력"
        author_info = slots.get("author_info", "")
        portfolio = _parse_service_items(slots.get("portfolio_projects") or "")
        learning = _parse_service_items(slots.get("learning_activities") or "")
        h1_text = author_info if author_info else business_name
        service_text = author_info or "포트폴리오"
        # note-card 3개: 포트폴리오 2개 + 학습 1개
        service_items = (portfolio[:2] + learning[:1])[:3]
        if not service_items and author_info:
            service_items = [{"name": author_info, "desc": ""}]
        faq_items = [
            {"q": "어떤 경력을 가지고 계신가요?", "a": service_text},
            {"q": "연락 방법이 어떻게 되나요?", "a": "전화 또는 이메일로 문의해 주세요."},
        ]

    else:
        main_field = _to_list(slots.get("core_services") or [])
        h1_text = business_name
        service_text = ", ".join(main_field[:2]) if main_field else "전문 서비스"
        service_items = [{"name": s, "desc": ""} for s in main_field[:4]]
        faq_items = [
            {"q": f"{business_name}의 {field_label}이 무엇인가요?",
             "a": f"{service_text}를 제공합니다."},
            {"q": "영업 시간이 어떻게 되나요?", "a": business_hours},
            {"q": "상담은 어떻게 신청하나요?", "a": "전화 또는 카카오톡으로 문의해 주세요."},
        ]

    quick_answer = f"{business_name}은(는) {service_text}를 제공하는 전문 업체입니다."

    jsonld: list[dict] = [{
        "@context": "https://schema.org",
        "@type": "LocalBusiness",
        "name": business_name,
        "telephone": phone,
        "openingHours": business_hours,
    }]
    if kakao_channel:
        jsonld[0]["sameAs"] = [f"https://pf.kakao.com/{kakao_channel}"]

    return {
        "schema_version": "1.0.0",
        "template_id": template_id,
        "template_category": template_category,
        "pages": [{
            "route": "/",
            "title_h1": h1_text,
            "seo": {
                "title": f"{business_name} | 공식 홈페이지",
                "description": f"{business_name}의 {service_text} 서비스. 지금 바로 상담받으세요.",
                "og": {
                    "title": f"{business_name} | 공식 홈페이지",
                    "description": f"{service_text} 전문 {business_name}",
                    "type": "website",
                },
            },
            "jsonld": jsonld,
            "blocks": [
                {"type": "Hero", "h1": h1_text, "subheadline": hero_subheadline, "featured_price": hero_featured_price},
                {"type": "Services", "items": service_items},
                {"type": "QuickAnswer", "text": quick_answer},
                {"type": "Contact", "phone": phone, "kakao": kakao_channel},
                {"type": "FAQ", "items": faq_items},
            ],
        }],
    }


def _inline_preview_css(html: str, site_id: str, s3_client: object) -> str:
    """./static/*.css 링크 태그를 S3에서 읽어 <style> 태그로 인라인 치환."""
    def _replace(m: re.Match) -> str:
        href = m.group(1)
        css_name = href.rsplit("/", 1)[-1]
        try:
            obj = s3_client.get_object(  # type: ignore[union-attr]
                Bucket=_ARTIFACTS_BUCKET,
                Key=f"sites/{site_id}/preview/static/{css_name}",
            )
            css = obj["Body"].read().decode("utf-8")
            return f"<style>{css}</style>"
        except Exception:
            return m.group(0)

    return re.sub(
        r'<link\b[^>]*\bhref=["\'](\./static/[^"\']+\.css)["\'][^>]*(?:/)?>',
        _replace,
        html,
        flags=re.IGNORECASE,
    )


def _build_contract(site_id: str) -> dict:
    """
    챗봇 수집 슬롯(7개) → Contract JSON (schema_version: 0.1.0).
    생성 에이전트(Bedrock)가 소비하는 확정 포맷.
    """
    o = _site_onboarding.get(site_id, {})

    business_name    = o.get("business_name", "")
    business_region  = o.get("business_region", "한국")
    core_services    = _to_list(o.get("core_services", []))
    target_audience  = _to_list(o.get("target_audience", ["잠재 고객"]))
    phone            = o.get("phone", "")
    kakao_raw        = o.get("kakao_channel", "")
    kakao_channel    = "" if kakao_raw in ("없음", "none", "") else kakao_raw
    business_hours   = o.get("business_hours", "평일 09:00-18:00")
    template_id      = o.get("template_id", "landing_general")
    category         = o.get("structure", "landing")

    slug_raw  = template_id.replace("landing_", "").replace("-landing", "")
    slug      = slug_raw.split("-")[0] if "-" in slug_raw else slug_raw

    contact_method = ["phone"] if phone else []
    if kakao_channel:
        contact_method.append("kakao")
    contact_method.append("contact_form")

    cta = (["무료 상담 신청", "카카오톡 상담"] if kakao_channel
           else ["무료 상담 신청", "전화 상담"])

    brand_keywords = ([business_name] + core_services[:2]) if business_name else ["전문 서비스"]

    required = bool(business_name and core_services and phone)
    slot_score = round(
        bool(business_name) * 0.25
        + bool(business_region) * 0.10
        + bool(core_services) * 0.25
        + bool(target_audience) * 0.15
        + bool(phone) * 0.15
        + bool(business_hours) * 0.10,
        2,
    )

    def _slot_status(val: object) -> dict:
        filled = bool(val)
        return {"status": "filled" if filled else "missing",
                "confidence": 1.0 if filled else 0,
                "source": "user" if filled else None,
                "ask_count": 1 if filled else 0}

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
            "business_name":         business_name,
            "industry":              o.get("industry", "general"),
            "business_type":         category,
            "business_region":       business_region,
            "site_goal":             "lead_capture",
            "target_audience":       target_audience,
            "core_services":         core_services,
            "pain_points":           [],
            "required_sections":     ["hero", "services", "faq", "contact_form", "footer"],
            "tone_style":            ["professional", "trustworthy"],
            "brand_keywords":        brand_keywords,
            "cta":                   cta,
            "contact_method":        contact_method,
            "phone":                 phone,
            "kakao_channel":         kakao_channel,
            "business_hours":        business_hours,
            "business_number":       None,
            "reference_site_exists": False,
            "reference_sites":       [],
        },
        "slot_status": {
            "business_name":   _slot_status(business_name),
            "business_region": _slot_status(business_region),
            "core_services":   _slot_status(core_services),
            "target_audience": _slot_status(target_audience),
            "phone":           _slot_status(phone),
            "kakao_channel":   {"status": "filled" if kakao_channel else "skipped",
                                "confidence": 1.0 if kakao_channel else 0,
                                "source": "user", "ask_count": 1},
            "business_hours":  _slot_status(business_hours),
            "business_number": {"status": "missing", "confidence": 0, "source": None, "ask_count": 0},
        },
        "evidence": {"wiki_refs": [], "research_refs": []},
        "gates": {
            "completeness_score": slot_score,
            "preview_ready":      True,
            "generation_ready":   required,
            "missing_items": [
                {"slot_key": k, "reason": f"{k} 필드가 누락되었습니다."}
                for k, v in [
                    ("business_name", business_name),
                    ("core_services", core_services),
                    ("phone", phone),
                ]
                if not v
            ],
            "unresolved_items": [],
        },
    }



@router.get("", response_model=SiteListResponse)
async def list_sites(
    current_user: Annotated[CurrentUser, Depends(require_authenticated)],
    site_service: Annotated[SiteService, Depends(get_site_service)],
) -> SiteListResponse:
    result = await site_service.list_sites(user_id=current_user.id)
    all_ids = [str(item.id) for item in result.items]
    domain_urls: dict[str, str] = {}
    if all_ids:
        ddb_data = await asyncio.to_thread(_batch_get_domain_urls_with_status, all_ids)
        domain_urls = {sid: d["domain_url"] for sid, d in ddb_data.items() if d.get("domain_url")}
        # DynamoDB published이지만 PostgreSQL is_published=False인 사이트 자동 동기화
        for item in result.items:
            sid = str(item.id)
            if not item.is_published and ddb_data.get(sid, {}).get("publish_status") == "published":
                item.is_published = True
                item.published_at = item.published_at  # 기존값 유지
                asyncio.create_task(
                    site_service.sync_published_from_pipeline(
                        user_id=current_user.id, site_id=item.id
                    )
                )
    for item in result.items:
        item.domain_url = domain_urls.get(str(item.id))
    return result


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


@router.patch("/{site_id}/onboarding/slots", status_code=status.HTTP_204_NO_CONTENT)
async def save_chat_slots(
    site_id: UUID,
    payload: dict,
    current_user: Annotated[CurrentUser, Depends(require_authenticated)],
) -> None:
    """챗봇 수집 슬롯 7개를 한 번에 저장."""
    sid = str(site_id)
    if sid not in _site_onboarding:
        _site_onboarding[sid] = {}
    _site_onboarding[sid].update(payload)


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
    preview_mode: str  # "p3" | "mock"
    preview_html: str | None = None
    preview_url: str | None = None
    message: str


@router.post("/{site_id}/preview", response_model=_PreviewResponse, status_code=status.HTTP_200_OK)
async def create_preview(
    site_id: UUID,
    current_user: Annotated[CurrentUser, Depends(require_authenticated)],
) -> _PreviewResponse:
    """
    Contract JSON → render_spec S3 업로드 → P3 Worker 호출 → HTML 반환.
    P3_BUILD_ENDPOINT 미설정 시 mock 응답.
    """
    sid = str(site_id)
    endpoint = settings.p3_build_endpoint
    if not endpoint:
        return _PreviewResponse(
            site_id=sid,
            preview_mode="mock",
            message="P3_BUILD_ENDPOINT 미설정 — 로컬 개발 모드입니다.",
        )

    # ✅ S3의 contract_final.json 우선 읽기 (P1 채팅 완료한 경우)
    # 없으면 database에서 읽기 (구 방식)
    s3 = boto3.client("s3", region_name=_AWS_REGION)
    contract = None
    try:
        obj = s3.get_object(Bucket=_ARTIFACTS_BUCKET, Key=f"sites/{sid}/contract_final.json")
        contract_data = json.loads(obj["Body"].read().decode("utf-8"))
        # contract_final.json은 1.0.0 스키마, 1.0.0 → 0.1.0 변환
        if contract_data.get("schema_version") == "1.0.0":
            # 1.0.0 → 0.1.0 변환
            contract = {
                "schema_version": "0.1.0",
                "ids": contract_data.get("ids", {}),
                "template": contract_data.get("template", {}),
                "slots": contract_data.get("slots", {}),
            }
            logger.info("preview: S3 contract_final.json 변환 사용 site=%s", sid)
        else:
            logger.warning("preview: contract_final schema mismatch, database 사용 site=%s", sid)
    except Exception as e:
        logger.warning("preview: S3 contract_final.json 읽기 실패 site=%s - %s, database에서 읽기", sid, e)
        contract = None

    if not contract:
        try:
            contract = _build_contract(sid)
        except Exception as e:
            logger.error("preview: _build_contract 실패 site=%s - %s", sid, e)
            return _PreviewResponse(
                site_id=sid,
                preview_mode="error",
                message=f"Contract 로드 실패: {str(e)[:100]}",
            )

    try:
        render_spec = _build_render_spec(contract)
    except Exception as e:
        logger.error("preview: _build_render_spec 실패 site=%s - %s", sid, e)
        return _PreviewResponse(
            site_id=sid,
            preview_mode="error",
            message=f"Render spec 생성 실패: {str(e)[:100]}",
        )

    s3 = boto3.client("s3", region_name=_AWS_REGION)

    # ✅ Preview용 render_spec → S3 (경로 분리: preview/render_spec.json)
    try:
        s3.put_object(
            Bucket=_ARTIFACTS_BUCKET,
            Key=f"sites/{sid}/preview/render_spec.json",
            Body=json.dumps(render_spec, ensure_ascii=False).encode("utf-8"),
            ContentType="application/json",
        )
    except (BotoCoreError, ClientError) as e:
        logger.error("render_spec S3 업로드 실패 site=%s: %s", sid, e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="render_spec 저장에 실패했습니다.",
        ) from e

    # P3 Worker 호출 (동기 HTTP — P3는 내부적으로 S3 읽기/쓰기)
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                f"{endpoint.rstrip('/')}/build",
                json={
                    "sessionId": str(sid),
                    "inputText": f"site_id={sid} mode=preview",
                    "sessionAttributes": {"site_id": str(sid), "mode": "preview"},
                },
            )
            resp.raise_for_status()
    except (httpx.HTTPStatusError, httpx.RequestError) as e:
        logger.error("P3 preview 호출 실패 site=%s: %s", sid, e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="프리뷰 생성 서비스에 연결할 수 없습니다.",
        ) from e

    # P3가 업로드한 HTML을 S3에서 읽어 CSS 인라인 후 반환
    try:
        obj = s3.get_object(Bucket=_ARTIFACTS_BUCKET, Key=f"sites/{sid}/preview/index.html")
        raw_html = obj["Body"].read().decode("utf-8")
        preview_html = _inline_preview_css(raw_html, sid, s3)
    except (BotoCoreError, ClientError) as e:
        logger.error("preview HTML S3 읽기 실패 site=%s: %s", sid, e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="프리뷰 HTML 조회에 실패했습니다.",
        ) from e

    return _PreviewResponse(
        site_id=sid,
        preview_mode="p3",
        preview_html=preview_html,
        message="프리뷰가 생성되었습니다.",
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
    pipeline_status: str          # "building"|"validating"|"provisioning"|"published"|"failed"|"unknown"
    domain_url: str | None = None
    render_spec_s3_key: str | None = None
    execution_arn: str | None = None
    updated_at: str | None = None
    error: str | None = None
    message: str | None = None


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
        s3 = _get_s3_client()
        contract_s3_key = f"sites/{sid}/contract_final.json"

        # 1) P1 chatbot이 저장한 S3 contract_final.json 우선 사용 (schema 1.0.0)
        contract_json: dict | None = None
        try:
            obj = s3.get_object(Bucket=_ARTIFACTS_BUCKET, Key=contract_s3_key)
            contract_json = json.loads(obj["Body"].read().decode("utf-8"))
            logger.info("publish: S3 contract_final.json 사용 site=%s schema=%s",
                        sid, contract_json.get("schema_version"))
        except ClientError as e:
            if e.response["Error"]["Code"] in ("NoSuchKey", "404"):
                pass  # 아직 P1 완료 안 됨 — mock으로 폴백
            else:
                logger.error("publish: S3 contract 읽기 실패 site=%s: %s", sid, e)
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="계약 데이터를 불러올 수 없습니다.",
                ) from e
        except BotoCoreError as e:
            logger.error("publish: S3 네트워크 오류 site=%s: %s", sid, e)
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="계약 데이터를 불러올 수 없습니다.",
            ) from e

        # 2) S3에 없으면 인메모리 mock으로 폴백 후 S3에 업로드
        if contract_json is None:
            contract_json = _build_contract(sid)
            logger.warning("publish: S3 contract 없음, mock 사용 site=%s", sid)
            if not contract_json.get("gates", {}).get("generation_ready"):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="채팅을 완료하여 홈페이지 정보를 입력해 주세요.",
                )
            try:
                s3.put_object(
                    Bucket=_ARTIFACTS_BUCKET,
                    Key=contract_s3_key,
                    Body=json.dumps(contract_json, ensure_ascii=False).encode("utf-8"),
                    ContentType="application/json",
                )
            except (BotoCoreError, ClientError) as e:
                logger.error("publish: S3 contract 업로드 실패 site=%s: %s", sid, e)
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="S3 업로드에 실패했습니다.",
                ) from e

        # 3) template_type, template_category 추출
        template_type, template_category = _extract_template_info(contract_json)

        # 4) Step Functions 실행
        try:
            pipeline_info = _start_pipeline(sid, template_type, template_category)
        except (BotoCoreError, ClientError) as e:
            logger.error("publish: Step Functions 실행 실패 site=%s: %s", sid, e)
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
    site_service: Annotated[SiteService, Depends(get_site_service)],
) -> _PipelineStatusResponse:
    """
    파이프라인 실행 상태 폴링용 엔드포인트.
    프론트엔드가 3초마다 호출하여 생성 에이전트 → 빌드 → 검증 → 배포 진행 상황 표시.
    published 감지 시 PostgreSQL is_published 동기화 (멱등적).
    """
    sid = str(site_id)
    if not _AWS_ENABLED:
        return _PipelineStatusResponse(
            site_id=sid,
            pipeline_status="published",
            message="로컬 모드",
        )
    result = _get_pipeline_status(sid)
    if result.get("pipeline_status") == "published":
        try:
            await site_service.sync_published_from_pipeline(
                user_id=current_user.id,
                site_id=site_id,
            )
        except Exception as e:
            logger.warning("pipeline/status: DB 동기화 실패 site=%s: %s", sid, e)
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
        client = boto3.client("bedrock-agentcore", region_name=_AWS_REGION)
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
        data: dict = await asyncio.get_running_loop().run_in_executor(_get_p1_executor(), _invoke)
    except (BotoCoreError, ClientError, ValueError) as e:
        logger.error("P1 AgentCore 오류 site=%s: %s", sid, e)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="챗봇 서비스에 일시적 오류가 발생했습니다.",
        ) from e
    except Exception as e:
        logger.error("P1 예상치 못한 오류 site=%s: %s", sid, e, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="챗봇 서비스에 일시적 오류가 발생했습니다.",
        ) from e

    logger.info("P1 응답 data=%s", data)
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
