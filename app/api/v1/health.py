import logging

from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.db.session import check_database_connection

logger = logging.getLogger(__name__)


class HealthResponse(BaseModel):
    status: str
    service: str
    db: bool


router = APIRouter(prefix="/health", tags=["Health"])


@router.get("", response_model=HealthResponse)
async def health_check() -> HealthResponse | JSONResponse:
    try:
        db_ok = await check_database_connection()
    except Exception:
        logger.exception("헬스체크 DB 연결 확인 실패")
        db_ok = False

    if not db_ok:
        # ALB 타겟그룹 헬스체크는 기본적으로 HTTP 상태 코드만 확인한다
        # (JSON 바디는 검사하지 않음). DB 장애를 실제로 감지해 태스크를
        # 교체하려면 200이 아닌 상태 코드를 반환해야 한다.
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={"status": "degraded", "service": "hezo-api", "db": False},
        )

    return HealthResponse(status="ok", service="hezo-api", db=True)
