import asyncio
import gzip
import json
import logging
import os
import re
import socket
import ssl
from datetime import datetime, timedelta, timezone
from io import BytesIO
from typing import Annotated
from urllib.parse import urlparse

import boto3
import httpx
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import CurrentUser, require_authenticated
from app.schemas.monitoring import (
    ActionItem,
    BotCrawls,
    GeoFiles,
    JsonLd,
    LlmsFullQuality,
    MonitoringHistory,
    MonitoringSnapshot,
    ResponseMsPoint,
    ScoreHistory,
    ScorePoint,
)

logger = logging.getLogger(__name__)

_AWS_REGION = os.environ.get("AWS_DEFAULT_REGION", "ap-northeast-2")
_PIPELINE_TABLE = os.environ.get("PIPELINE_TABLE", "hezo_pipeline_state")
_REPORT_TABLE = "report_scores"
_CF_LOG_BUCKET = os.environ.get("CF_LOG_BUCKET", "hezo-cloudfront-logs")
_PAGESPEED_API_KEY = os.environ.get("PAGESPEED_API_KEY")
_SNAPSHOT_CACHE_HOURS = 24
_HTTP_TIMEOUT = 5.0

_BOT_PATTERNS: dict[str, re.Pattern] = {
    "gpt_bot": re.compile(r"GPTBot", re.I),
    "claude_bot": re.compile(r"ClaudeBot", re.I),
    "perplexity_bot": re.compile(r"PerplexityBot", re.I),
    "yeti": re.compile(r"Yeti", re.I),
}

router = APIRouter(prefix="/sites/{site_id}/monitoring", tags=["Monitoring"])


# ── 헬퍼 함수 ──────────────────────────────────────────────────────────────

def _extract_json_ld_types(html: str) -> set[str]:
    found: set[str] = set()
    pattern = re.compile(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        re.DOTALL | re.IGNORECASE,
    )
    for match in pattern.finditer(html):
        try:
            data = json.loads(match.group(1).strip())
            t = data.get("@type", "")
            if t:
                found.add(t)
        except Exception:
            pass
    return found


def _geo_files_status(responses: dict[str, int]) -> dict[str, bool]:
    return {key: (code == 200) for key, code in responses.items()}


def _parse_llms_full_quality(content: str) -> dict:
    if not content:
        return {"faq_count": 0, "char_count": 0, "has_core_services": False, "has_faq": False, "has_core_pages": False}
    faq_count = len(re.findall(r"^Q:", content, re.MULTILINE))
    return {
        "faq_count": faq_count,
        "char_count": len(content),
        "has_core_services": "## 핵심 서비스" in content,
        "has_faq": "## FAQ" in content,
        "has_core_pages": "## 핵심 페이지" in content,
    }


def _check_ssl_expiry(hostname: str) -> int | None:
    try:
        ctx = ssl.create_default_context()
        with ctx.wrap_socket(
            socket.create_connection((hostname, 443), timeout=5),
            server_hostname=hostname,
        ) as s:
            cert = s.getpeercert()
        not_after = datetime.strptime(
            cert["notAfter"], "%b %d %H:%M:%S %Y %Z"
        ).replace(tzinfo=timezone.utc)
        return max(0, (not_after - datetime.now(timezone.utc)).days)
    except Exception:
        return None


async def _measure_site(domain_url: str) -> dict:
    parsed = urlparse(domain_url)
    hostname = parsed.hostname or domain_url
    base = domain_url.rstrip("/")

    geo_paths = {
        "llms_txt": f"{base}/llms.txt",
        "llms_full_txt": f"{base}/llms-full.txt",
        "sitemap_xml": f"{base}/sitemap.xml",
        "robots_txt": f"{base}/robots.txt",
    }

    geo_codes: dict[str, int] = {}
    html_body = ""
    response_ms: int | None = None

    async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT, follow_redirects=True) as client:
        # 응답 시간 + HTML (JSON-LD 파싱용)
        try:
            import time
            t0 = time.monotonic()
            r = await client.get(base)
            response_ms = int((time.monotonic() - t0) * 1000)
            if r.status_code == 200:
                html_body = r.text
        except Exception:
            pass

        # GEO 파일 상태 코드 (llms-full.txt는 GET으로 내용 파싱)
        llms_full_content = ""
        for key, url in geo_paths.items():
            try:
                if key == "llms_full_txt":
                    r = await client.get(url)
                    geo_codes[key] = r.status_code
                    if r.status_code == 200:
                        llms_full_content = r.text
                else:
                    r = await client.head(url)
                    geo_codes[key] = r.status_code
            except Exception:
                geo_codes[key] = 0

    json_ld_types = _extract_json_ld_types(html_body)
    ssl_days = await asyncio.to_thread(_check_ssl_expiry, hostname)

    pagespeed_mobile: int | None = None
    pagespeed_desktop: int | None = None
    if _PAGESPEED_API_KEY:
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                ps_url = (
                    f"https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
                    f"?url={domain_url}&key={_PAGESPEED_API_KEY}"
                )
                for strategy, target in [("mobile", "pagespeed_mobile"), ("desktop", "pagespeed_desktop")]:
                    r = await client.get(ps_url + f"&strategy={strategy}")
                    if r.status_code == 200:
                        score = (
                            r.json()
                            .get("lighthouseResult", {})
                            .get("categories", {})
                            .get("performance", {})
                            .get("score")
                        )
                        if score is not None:
                            if target == "pagespeed_mobile":
                                pagespeed_mobile = int(score * 100)
                            else:
                                pagespeed_desktop = int(score * 100)
        except Exception:
            pass

    return {
        "geo_files": _geo_files_status(geo_codes),
        "json_ld": {
            "local_business": "LocalBusiness" in json_ld_types,
            "faq_page": "FAQPage" in json_ld_types,
            "service": "Service" in json_ld_types,
        },
        "ssl_expiry_days": ssl_days,
        "response_ms": response_ms,
        "pagespeed_mobile": pagespeed_mobile,
        "pagespeed_desktop": pagespeed_desktop,
        "llms_full_quality": _parse_llms_full_quality(llms_full_content),
    }


def _get_domain_url(site_id: str) -> str | None:
    try:
        ddb = boto3.client("dynamodb", region_name=_AWS_REGION)
        resp = ddb.get_item(
            TableName=_PIPELINE_TABLE,
            Key={"site_id": {"S": site_id}},
        )
        item = resp.get("Item", {})
        return item.get("domain_url", {}).get("S")
    except (BotoCoreError, ClientError) as e:
        logger.warning("DDB get domain_url 실패 site=%s: %s", site_id, e)
        return None


def _get_cf_distribution_id(site_id: str) -> str | None:
    try:
        ddb = boto3.client("dynamodb", region_name=_AWS_REGION)
        resp = ddb.get_item(
            TableName=_PIPELINE_TABLE,
            Key={"site_id": {"S": site_id}},
        )
        item = resp.get("Item", {})
        return item.get("cloudfront_distribution_id", {}).get("S")
    except (BotoCoreError, ClientError) as e:
        logger.warning("DDB get cf_dist_id 실패 site=%s: %s", site_id, e)
        return None


def _parse_cf_logs_for_bots(site_id: str, cf_dist_id: str, days: int = 7) -> dict[str, int]:
    """S3 CloudFront 표준 로그에서 AI 봇 User-Agent를 집계한다.

    로그 파일 경로: s3://{CF_LOG_BUCKET}/{site_id}/{dist_id}.YYYY-MM-DD-HH.{unique}.gz
    CloudFront 로그 포맷(tab 구분): date time x-edge-location sc-bytes c-ip cs-method cs(Host)
      cs-uri-stem sc-status cs(Referer) cs(User-Agent) ...  (User-Agent = index 10, 0-based)
    """
    counts: dict[str, int] = {"gpt_bot": 0, "claude_bot": 0, "perplexity_bot": 0, "yeti": 0}
    cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).date()
    s3 = boto3.client("s3", region_name=_AWS_REGION)
    prefix = f"{site_id}/{cf_dist_id}."

    try:
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=_CF_LOG_BUCKET, Prefix=prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                # 파일명: {prefix}{dist}.YYYY-MM-DD-HH.{unique}.gz → date는 세 번째 .(역순 두 번째)
                parts = key.split(".")
                try:
                    log_date_str = parts[-3][:10]  # YYYY-MM-DD
                    if log_date_str < cutoff.isoformat():
                        continue
                except (IndexError, ValueError):
                    pass

                try:
                    body = s3.get_object(Bucket=_CF_LOG_BUCKET, Key=key)["Body"].read()
                    with gzip.open(BytesIO(body)) as f:
                        for raw_line in f:
                            line = raw_line.decode("utf-8", errors="ignore")
                            if line.startswith("#"):
                                continue
                            fields = line.split("\t")
                            if len(fields) <= 10:
                                continue
                            ua = fields[10]
                            for bot_key, pattern in _BOT_PATTERNS.items():
                                if pattern.search(ua):
                                    counts[bot_key] += 1
                except Exception as e:
                    logger.warning("CF 로그 파싱 실패 key=%s: %s", key, e)
    except Exception as e:
        logger.warning("CF 로그 목록 조회 실패 site=%s: %s", site_id, e)

    return counts


def _load_latest_snapshot(site_id: str) -> dict | None:
    """report_scores DDB에서 최근 24시간 이내 캐시 조회."""
    try:
        ddb = boto3.client("dynamodb", region_name=_AWS_REGION)
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=_SNAPSHOT_CACHE_HOURS)).isoformat()
        resp = ddb.query(
            TableName=_REPORT_TABLE,
            KeyConditionExpression="pk = :pk AND sk >= :cutoff",
            ExpressionAttributeValues={
                ":pk": {"S": f"SITE#{site_id}"},
                ":cutoff": {"S": f"REPORT#{cutoff}"},
            },
            ScanIndexForward=False,
            Limit=1,
        )
        items = resp.get("Items", [])
        if not items:
            return None
        item = items[0]
        # snapshot 타입만 반환
        if item.get("record_type", {}).get("S") != "snapshot":
            return None
        raw = item.get("payload", {}).get("S")
        if raw:
            return json.loads(raw)
        return None
    except Exception as e:
        logger.warning("DDB snapshot 캐시 조회 실패 site=%s: %s", site_id, e)
        return None


def _save_snapshot(site_id: str, data: dict) -> None:
    now = datetime.now(timezone.utc).isoformat()
    try:
        ddb = boto3.client("dynamodb", region_name=_AWS_REGION)
        ddb.put_item(
            TableName=_REPORT_TABLE,
            Item={
                "pk": {"S": f"SITE#{site_id}"},
                "sk": {"S": f"REPORT#{now}"},
                "record_type": {"S": "snapshot"},
                "payload": {"S": json.dumps(data)},
                "measured_at": {"S": now},
            },
        )
    except Exception as e:
        logger.warning("DDB snapshot 저장 실패 site=%s: %s", site_id, e)


# ── 엔드포인트 ──────────────────────────────────────────────────────────────

@router.get("/snapshot", response_model=MonitoringSnapshot)
async def get_snapshot(
    site_id: str,
    current_user: Annotated[CurrentUser, Depends(require_authenticated)],
) -> MonitoringSnapshot:
    domain_url = _get_domain_url(site_id)
    if not domain_url:
        raise HTTPException(status_code=404, detail="사이트 domain_url 없음 (미발급 상태)")

    cached = _load_latest_snapshot(site_id)
    if cached:
        raw_lq = cached.get("llms_full_quality")
        return MonitoringSnapshot(
            geo_files=GeoFiles(**cached["geo_files"]),
            json_ld=JsonLd(**cached["json_ld"]),
            ssl_expiry_days=cached.get("ssl_expiry_days"),
            response_ms=cached.get("response_ms"),
            pagespeed_mobile=cached.get("pagespeed_mobile"),
            pagespeed_desktop=cached.get("pagespeed_desktop"),
            llms_full_quality=LlmsFullQuality(**raw_lq) if raw_lq else None,
            last_measured_at=cached["last_measured_at"],
            from_cache=True,
        )

    now = datetime.now(timezone.utc).isoformat()
    measured = await _measure_site(domain_url)
    measured["last_measured_at"] = now
    _save_snapshot(site_id, measured)

    raw_lq = measured.get("llms_full_quality")
    return MonitoringSnapshot(
        geo_files=GeoFiles(**measured["geo_files"]),
        json_ld=JsonLd(**measured["json_ld"]),
        ssl_expiry_days=measured.get("ssl_expiry_days"),
        response_ms=measured.get("response_ms"),
        pagespeed_mobile=measured.get("pagespeed_mobile"),
        pagespeed_desktop=measured.get("pagespeed_desktop"),
        llms_full_quality=LlmsFullQuality(**raw_lq) if raw_lq else None,
        last_measured_at=now,
        from_cache=False,
    )


def _build_history_from_items(
    items: list[dict], days: int = 7
) -> list[dict]:
    today = datetime.now(timezone.utc).date()
    date_map: dict[str, int | None] = {
        (today - timedelta(days=i)).isoformat(): None for i in range(days - 1, -1, -1)
    }
    for item in items:
        d = item.get("date")
        if d and d in date_map:
            date_map[d] = item.get("response_ms")
    return [{"date": d, "value": v} for d, v in date_map.items()]


def _load_history(site_id: str, days: int = 7) -> list[dict]:
    try:
        ddb = boto3.client("dynamodb", region_name=_AWS_REGION)
        start = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        resp = ddb.query(
            TableName=_REPORT_TABLE,
            KeyConditionExpression="pk = :pk AND sk >= :start",
            FilterExpression="record_type = :t",
            ExpressionAttributeValues={
                ":pk": {"S": f"SITE#{site_id}"},
                ":start": {"S": f"REPORT#{start}"},
                ":t": {"S": "snapshot"},
            },
        )
        items = []
        for item in resp.get("Items", []):
            raw = item.get("payload", {}).get("S")
            measured_at = item.get("measured_at", {}).get("S", "")
            if raw and measured_at:
                payload = json.loads(raw)
                items.append({
                    "date": measured_at[:10],
                    "response_ms": payload.get("response_ms"),
                })
        return items
    except Exception as e:
        logger.warning("DDB history 조회 실패 site=%s: %s", site_id, e)
        return []


@router.get("/history", response_model=MonitoringHistory)
async def get_history(
    site_id: str,
    current_user: Annotated[CurrentUser, Depends(require_authenticated)],
) -> MonitoringHistory:
    raw_items = _load_history(site_id, days=7)
    history = _build_history_from_items(raw_items, days=7)

    cf_dist_id = await asyncio.to_thread(_get_cf_distribution_id, site_id)
    if cf_dist_id:
        counts = await asyncio.to_thread(_parse_cf_logs_for_bots, site_id, cf_dist_id)
        bot_crawls = BotCrawls(**counts)
        bot_crawls_available = True
    else:
        bot_crawls = BotCrawls()
        bot_crawls_available = False

    return MonitoringHistory(
        response_ms_history=[ResponseMsPoint(**p) for p in history],
        bot_crawls=bot_crawls,
        bot_crawls_available=bot_crawls_available,
    )


def _load_score_history(site_id: str, days: int = 90) -> list[dict]:
    """report_scores DDB에서 리포트 에이전트가 저장한 weekly overall_score 조회."""
    try:
        ddb = boto3.client("dynamodb", region_name=_AWS_REGION)
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%d")
        resp = ddb.query(
            TableName=_REPORT_TABLE,
            KeyConditionExpression="pk = :pk AND sk BETWEEN :start AND :end",
            ExpressionAttributeValues={
                ":pk": {"S": f"SITE#{site_id}"},
                ":start": {"S": f"REPORT#{cutoff}"},
                ":end": {"S": "REPORT#9999"},
            },
            ScanIndexForward=True,
        )
        result = []
        for item in resp.get("Items", []):
            sk = item.get("sk", {}).get("S", "")
            if not sk.startswith("REPORT#"):
                continue
            score_n = item.get("overall_score", {}).get("N")
            if score_n is None:
                continue
            result.append({
                "date": sk.replace("REPORT#", ""),
                "score": int(float(score_n)),
                "delta": int(float(item.get("delta", {}).get("N", "0"))),
                "action_items_raw": item.get("action_items", {}).get("S", "[]"),
            })
        return result
    except Exception as e:
        logger.warning("score_history 조회 실패 site=%s: %s", site_id, e)
        return []


def _parse_action_items(raw: str) -> list[ActionItem]:
    """Haiku가 생성한 액션 아이템 JSON을 ActionItem 리스트로 변환."""
    try:
        items = json.loads(raw)
        result = []
        for item in items:
            if isinstance(item, dict):
                text = item.get("text", item.get("action", str(item)))
                level_raw = item.get("level", item.get("priority", "yellow")).lower()
            else:
                text = str(item)
                level_raw = "yellow"
            # 🔴→red, 🟡→yellow, 🟢→green 이모지 변환
            if "🔴" in text or "red" in level_raw or "high" in level_raw:
                level = "red"
                text = text.replace("🔴", "").strip()
            elif "🟢" in text or "green" in level_raw or "low" in level_raw:
                level = "green"
                text = text.replace("🟢", "").strip()
            else:
                level = "yellow"
                text = text.replace("🟡", "").strip()
            result.append(ActionItem(level=level, text=text))
        return result
    except Exception:
        return []


@router.get("/score-history", response_model=ScoreHistory)
async def get_score_history(
    site_id: str,
    current_user: Annotated[CurrentUser, Depends(require_authenticated)],
) -> ScoreHistory:
    """리포트 에이전트가 주 1회 측정한 AI 가시성 종합점수 히스토리 (최대 90일)."""
    items = _load_score_history(site_id, days=90)

    if not items:
        return ScoreHistory(score_history=[], latest_score=None, latest_delta=0, action_items=[])

    score_history = [ScorePoint(date=it["date"], score=it["score"], delta=it["delta"]) for it in items]
    latest = items[-1]
    action_items = _parse_action_items(latest["action_items_raw"])

    return ScoreHistory(
        score_history=score_history,
        latest_score=latest["score"],
        latest_delta=latest["delta"],
        action_items=action_items,
    )
