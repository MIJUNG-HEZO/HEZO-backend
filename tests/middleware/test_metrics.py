import time
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.middleware.metrics import MetricsMiddleware


@pytest.fixture
def app_with_metrics():
    app = FastAPI()

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    with patch("app.middleware.metrics.boto3") as mock_boto3:
        mock_cw = MagicMock()
        mock_boto3.client.return_value = mock_cw
        app.add_middleware(MetricsMiddleware, cloudwatch_namespace="HEZO/Test")
        yield app, mock_cw


def test_x_response_time_header_present(app_with_metrics):
    app, _ = app_with_metrics
    client = TestClient(app)
    response = client.get("/ping")
    assert "X-Response-Time" in response.headers
    assert response.headers["X-Response-Time"].endswith("ms")


def test_x_response_time_is_numeric(app_with_metrics):
    app, _ = app_with_metrics
    client = TestClient(app)
    response = client.get("/ping")
    value = response.headers["X-Response-Time"].replace("ms", "")
    assert float(value) >= 0


def test_latency_accumulates():
    app = FastAPI()

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    with patch("app.middleware.metrics.boto3"):
        middleware = MetricsMiddleware(app, cloudwatch_namespace="HEZO/Test")
        client = TestClient(middleware)
        for _ in range(5):
            client.get("/ping")
        assert len(middleware._latencies) == 5


def test_percentile_calculation():
    with patch("app.middleware.metrics.boto3"):
        from app.middleware.metrics import MetricsMiddleware
        from fastapi import FastAPI
        m = MetricsMiddleware(FastAPI())
        latencies = list(range(1, 101))  # 1~100ms
        assert m._percentile(latencies, 95) == 95
        assert m._percentile(latencies, 99) == 99


def test_flush_calls_cloudwatch():
    app = FastAPI()

    @app.get("/ping")
    async def ping():
        return {"ok": True}

    with patch("app.middleware.metrics.boto3") as mock_boto3:
        mock_cw = MagicMock()
        mock_boto3.client.return_value = mock_cw

        middleware = MetricsMiddleware(app, cloudwatch_namespace="HEZO/Test")
        client = TestClient(middleware)
        middleware._latencies.extend([100.0, 200.0, 300.0])
        middleware._last_flush = 0  # 강제 flush 유발

        client.get("/ping")

        mock_cw.put_metric_data.assert_called_once()
        call_kwargs = mock_cw.put_metric_data.call_args[1]
        assert call_kwargs["Namespace"] == "HEZO/Test"
        metric_names = {m["MetricName"] for m in call_kwargs["MetricData"]}
        assert {"P95Latency", "P99Latency", "RPS"} == metric_names
