from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.integrations.payments.toss_payments_client import TossPaymentsClient


def test_toss_payments_client_creates_payment_window_params_from_domain_objects() -> None:
    payment_request_id = uuid4()
    payment_request = SimpleNamespace(id=payment_request_id)
    plan = SimpleNamespace(code="PRO", name="Pro", price_monthly=29000)
    user = SimpleNamespace(email="user@example.com")
    client = TossPaymentsClient(
        success_url="http://localhost:3000/billing/success",
        fail_url="http://localhost:3000/billing/fail",
    )

    params = client.create_payment_request_params(
        payment_request=payment_request,
        plan=plan,
        user=user,
    )

    assert params.amount == 29000
    assert params.order_id == str(payment_request_id)
    assert len(params.order_id) == 36
    assert set(params.order_id) <= set("0123456789abcdef-")
    assert params.order_name == "HEZO Pro Plan"
    assert params.customer_email == "user@example.com"
    assert params.success_url == "http://localhost:3000/billing/success"
    assert params.fail_url == "http://localhost:3000/billing/fail"


def test_toss_payment_request_params_returns_toss_sdk_payload_keys() -> None:
    payment_request_id = uuid4()
    client = TossPaymentsClient(
        success_url="https://hezo.example.com/success",
        fail_url="https://hezo.example.com/fail",
    )

    payload = client.create_payment_request_params(
        payment_request=SimpleNamespace(id=payment_request_id),
        plan=SimpleNamespace(code="MAX", name="Max", price_monthly=99000),
        user=SimpleNamespace(email="max@example.com"),
    ).to_payload()

    assert payload == {
        "amount": 99000,
        "orderId": str(payment_request_id),
        "orderName": "HEZO Max Plan",
        "customerEmail": "max@example.com",
        "successUrl": "https://hezo.example.com/success",
        "failUrl": "https://hezo.example.com/fail",
    }


def test_toss_payments_client_uses_configured_default_urls() -> None:
    client = TossPaymentsClient()

    params = client.create_payment_request_params(
        payment_request=SimpleNamespace(id=uuid4()),
        plan=SimpleNamespace(code="PRO", name="Pro", price_monthly=29000),
        user=SimpleNamespace(email="user@example.com"),
    )

    assert params.success_url.endswith("/billing/success")
    assert params.fail_url.endswith("/billing/fail")


def test_toss_payments_client_allows_missing_customer_email() -> None:
    params = TossPaymentsClient(
        success_url="https://hezo.example.com/success",
        fail_url="https://hezo.example.com/fail",
    ).create_payment_request_params(
        payment_request=SimpleNamespace(id=uuid4()),
        plan=SimpleNamespace(code="PRO", name="Pro", price_monthly=29000),
        user=SimpleNamespace(email=None),
    )

    assert params.customer_email is None
    assert params.to_payload()["customerEmail"] is None


def test_toss_payments_client_requires_plan_name_for_order_name() -> None:
    with pytest.raises(ValueError, match="Plan name is required"):
        TossPaymentsClient().create_payment_request_params(
            payment_request=SimpleNamespace(id=uuid4()),
            plan=SimpleNamespace(code="PRO", name="", price_monthly=29000),
            user=SimpleNamespace(email="user@example.com"),
        )
