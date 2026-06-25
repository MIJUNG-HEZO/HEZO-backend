import json
import logging
import os
import re
import socket
import ssl
from datetime import datetime, timedelta, timezone
from typing import Annotated
from urllib.parse import urlparse

import boto3
import httpx
from botocore.exceptions import BotoCoreError, ClientError
from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import CurrentUser, require_authenticated
from app.schemas.monitoring import (
    BotCrawls,
    GeoFiles,
    JsonLd,
    MonitoringHistory,
    MonitoringSnapshot,
    ResponseMsPoint,
)

logger = logging.getLogger(__name__)

_AWS_REGION = os.environ.get("AWS_DEFAULT_REGION", "ap-northeast-2")
_PIPELINE_TABLE = os.environ.get("PIPELINE_TABLE", "hezo_pipeline_state")
_REPORT_TABLE = "report_scores"
_PAGESPEED_API_KEY = os.environ.get("PAGESPEED_API_KEY")
_SNAPSHOT_CACHE_HOURS = 24
_HTTP_TIMEOUT = 5.0

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

        # GEO 파일 상태 코드
        for key, url in geo_paths.items():
            try:
                r = await client.head(url)
                geo_codes[key] = r.status_code
            except Exception:
                geo_codes[key] = 0

    json_ld_types = _extract_json_ld_types(html_body)
    ssl_days = _check_ssl_expiry(hostname)

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
        return MonitoringSnapshot(
            geo_files=GeoFiles(**cached["geo_files"]),
            json_ld=JsonLd(**cached["json_ld"]),
            ssl_expiry_days=cached.get("ssl_expiry_days"),
            response_ms=cached.get("response_ms"),
            pagespeed_mobile=cached.get("pagespeed_mobile"),
            pagespeed_desktop=cached.get("pagespeed_desktop"),
            last_measured_at=cached["last_measured_at"],
            from_cache=True,
        )

    now = datetime.now(timezone.utc).isoformat()
    measured = await _measure_site(domain_url)
    measured["last_measured_at"] = now
    _save_snapshot(site_id, measured)

    return MonitoringSnapshot(
        geo_files=GeoFiles(**measured["geo_files"]),
        json_ld=JsonLd(**measured["json_ld"]),
        ssl_expiry_days=measured.get("ssl_expiry_days"),
        response_ms=measured.get("response_ms"),
        pagespeed_mobile=measured.get("pagespeed_mobile"),
        pagespeed_desktop=measured.get("pagespeed_desktop"),
        last_measured_at=now,
        from_cache=False,
    )
