"""프로젝트 전역 서킷브레이커 레지스트리.

각 브레이커는 독립적인 장애 지점을 감싼다 — 하나가 open되어도
나머지 경로에는 영향을 주지 않는다. 기본 설정: 연속 5회 실패 시
open, 60초 후 half-open으로 재시도.
"""

import pybreaker

sqs_publish_breaker = pybreaker.CircuitBreaker(
    fail_max=5,
    reset_timeout=60,
    name="sqs-site-publish",
)
dynamodb_site_queue_breaker = pybreaker.CircuitBreaker(
    fail_max=5,
    reset_timeout=60,
    name="dynamodb-site-queue",
)
aurora_site_insert_breaker = pybreaker.CircuitBreaker(
    fail_max=5,
    reset_timeout=60,
    name="aurora-site-insert",
)
redis_plans_cache_breaker = pybreaker.CircuitBreaker(
    fail_max=5,
    reset_timeout=60,
    name="redis-plans-cache",
)
