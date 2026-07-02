from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.logging import trace_id_var
from app.main import TraceIdMiddleware


def test_trace_id_middleware_resets_context_after_request():
    app = FastAPI()
    app.add_middleware(TraceIdMiddleware)

    captured = {}

    @app.get("/probe")
    def probe():
        captured["value_during_request"] = trace_id_var.get()
        return {"ok": True}

    client = TestClient(app)
    resp = client.get("/probe")

    assert resp.status_code == 200
    assert captured["value_during_request"] == ""
    assert trace_id_var.get() == ""
