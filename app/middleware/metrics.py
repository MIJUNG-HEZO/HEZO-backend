import asyncio
import time
from collections import deque
from threading import Lock

import boto3


class MetricsMiddleware:
    def __init__(self, app, cloudwatch_namespace: str = "HEZO/Performance"):
        self.app = app
        self._lock = Lock()
        self._latencies: deque[float] = deque(maxlen=10_000)
        self._last_flush: float = time.time()
        self._flush_interval: float = 30.0
        self._namespace = cloudwatch_namespace
        self._cw = None

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start = time.perf_counter()

        async def send_wrapper(message):
            if message["type"] == "http.response.start":
                headers = dict(message.get("headers", []))
                elapsed_ms = (time.perf_counter() - start) * 1000
                headers[b"x-response-time"] = f"{elapsed_ms:.1f}ms".encode()
                message = {**message, "headers": list(headers.items())}
            await send(message)

        await self.app(scope, receive, send_wrapper)

        elapsed_ms = (time.perf_counter() - start) * 1000
        now = time.time()
        latencies_snapshot = None

        with self._lock:
            self._latencies.append(elapsed_ms)
            if (now - self._last_flush) >= self._flush_interval:
                self._last_flush = now
                latencies_snapshot = list(self._latencies)
                self._latencies.clear()

        if latencies_snapshot:
            await asyncio.to_thread(self._flush, latencies_snapshot)

    @staticmethod
    def _percentile(latencies: list[float], p: int) -> float:
        if not latencies:
            return 0.0
        sorted_lats = sorted(latencies)
        idx = max(0, int(len(sorted_lats) * p / 100) - 1)
        return sorted_lats[idx]

    def _get_cw_client(self):
        if self._cw is None:
            self._cw = boto3.client("cloudwatch", region_name="ap-northeast-2")
        return self._cw

    def _flush(self, latencies: list[float]) -> None:
        p95 = self._percentile(latencies, 95)
        p99 = self._percentile(latencies, 99)
        rps = len(latencies) / self._flush_interval
        try:
            cw = self._get_cw_client()
            cw.put_metric_data(
                Namespace=self._namespace,
                MetricData=[
                    {"MetricName": "P95Latency", "Value": p95, "Unit": "Milliseconds"},
                    {"MetricName": "P99Latency", "Value": p99, "Unit": "Milliseconds"},
                    {"MetricName": "RPS", "Value": rps, "Unit": "Count/Second"},
                ],
            )
        except Exception:
            pass  # CloudWatch 실패는 API 응답에 영향 주지 않음
