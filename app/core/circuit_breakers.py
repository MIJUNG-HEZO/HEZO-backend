"""프로젝트 전역 서킷브레이커 레지스트리.

각 브레이커는 독립적인 장애 지점을 감싼다 — 하나가 open되어도
나머지 경로에는 영향을 주지 않는다. 기본 설정: 연속 5회 실패 시
open, 60초 후 half-open으로 재시도.
"""

import contextlib
from collections.abc import Coroutine
from datetime import UTC, datetime, timedelta
from typing import Any

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

def _check_and_maybe_half_open(breaker: pybreaker.CircuitBreaker) -> None:
    """pybreaker.CircuitOpenState.before_call()과 동일한 open/half-open 판단을
    재현한다. call_breaker_async()가 이걸 직접 재현하는 이유는 아래 참고."""
    if breaker.current_state != "open":
        return
    timeout = timedelta(seconds=breaker.reset_timeout)
    opened_at = breaker._state_storage.opened_at  # noqa: SLF001
    if opened_at and datetime.now(UTC) < opened_at + timeout:
        error_msg = f"Timeout not elapsed yet, {breaker.name} breaker still open"
        raise pybreaker.CircuitBreakerError(error_msg)
    breaker.half_open()


async def call_breaker_async[T](
    breaker: pybreaker.CircuitBreaker, coro: Coroutine[Any, Any, T]
) -> T:
    """서킷브레이커로 async 코루틴을 감싼다.

    설치된 pybreaker==1.4.1의 `CircuitBreaker.call_async()`는 내부적으로
    `tornado.gen`을 참조하는데 이 심볼을 어디서도 import하지 않아(tornado
    설치 여부와 무관하게) 호출 즉시 `NameError: name 'gen' is not defined`가
    발생한다(pybreaker 자체 버그, 세션 121 실측으로 4곳에서 재현 확인). 대신
    open 여부만 pybreaker의 상태전이 로직을 그대로 재현해 선체크하고, 실제
    코루틴은 이 이벤트루프에서 직접 await한 뒤 결과를 `breaker.call()`(동기,
    정상 동작)에 재전달해 성공/실패 카운팅과 half-open→open/closed 전이를
    pybreaker 공개 API로만 수행한다.
    """
    try:
        _check_and_maybe_half_open(breaker)
    except BaseException:
        coro.close()  # open이라 실행 안 될 코루틴을 미실행 상태로 방치하지 않는다
        raise
    try:
        result = await coro
    except BaseException as exc:
        error = exc

        def _reraise() -> None:
            raise error

        with contextlib.suppress(type(error)):
            breaker.call(_reraise)
        raise
    else:
        breaker.call(lambda: None)
        return result
