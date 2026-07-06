from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from opentelemetry import trace as otel_trace
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from app.api.v1.router import api_router
from app.core.config import settings
from app.core.exceptions import (
    AppException,
    app_exception_handler,
    request_validation_exception_handler,
    unhandled_exception_handler,
)
from app.core.logging import configure_json_logging, trace_id_var
from app.core.otel import setup_otel
from app.middleware.metrics import MetricsMiddleware
from app.middleware.rate_limit import RateLimitMiddleware


class TraceIdMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        span = otel_trace.get_current_span()
        span_context = span.get_span_context()
        trace_id = format(span_context.trace_id, "032x") if span_context.is_valid else ""
        token = trace_id_var.set(trace_id)
        try:
            return await call_next(request)
        finally:
            trace_id_var.reset(token)


def create_app() -> FastAPI:
    docs_enabled = not settings.is_production
    app = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )

    setup_otel(app)
    configure_json_logging()

    app.add_middleware(TraceIdMiddleware)

    # 프론트엔드 연동을 위한 CORS 허용 출처는 환경변수로 관리한다.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(MetricsMiddleware, cloudwatch_namespace="HEZO/Performance")

    # Redis 활성화 시에만 IP당 슬라이딩 윈도우 Rate Limiting을 적용한다.
    if settings.redis_enabled:
        app.add_middleware(
            RateLimitMiddleware,
            redis_url=settings.redis_url,
            limit=300,
            window_seconds=60,
        )

    app.include_router(api_router, prefix=settings.api_v1_prefix)
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(RequestValidationError, request_validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
    return app


app = create_app()
