import pybreaker

from app.core.circuit_breakers import (
    aurora_site_insert_breaker,
    dynamodb_site_queue_breaker,
    redis_plans_cache_breaker,
    sqs_publish_breaker,
)


def test_four_independent_breakers_exist() -> None:
    breakers = [
        sqs_publish_breaker,
        dynamodb_site_queue_breaker,
        aurora_site_insert_breaker,
        redis_plans_cache_breaker,
    ]
    for breaker in breakers:
        assert isinstance(breaker, pybreaker.CircuitBreaker)

    # 서로 다른 독립 인스턴스여야 한다 (하나가 open돼도 나머지에 영향 없어야 함)
    assert len({id(b) for b in breakers}) == 4


def test_breakers_default_config() -> None:
    for breaker in [
        sqs_publish_breaker,
        dynamodb_site_queue_breaker,
        aurora_site_insert_breaker,
        redis_plans_cache_breaker,
    ]:
        assert breaker.fail_max == 5
        assert breaker.reset_timeout == 60
