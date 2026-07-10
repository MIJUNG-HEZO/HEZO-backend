from unittest.mock import patch

from fastapi import FastAPI

from app.core.otel import setup_otel

_EXPORTER_PATCHES = (
    "opentelemetry.exporter.otlp.proto.grpc.trace_exporter.OTLPSpanExporter",
    "opentelemetry.exporter.otlp.proto.grpc.metric_exporter.OTLPMetricExporter",
)


def test_setup_otel_is_noop_without_endpoint(monkeypatch):
    monkeypatch.delenv("OTEL_EXPORTER_OTLP_ENDPOINT", raising=False)

    with patch(
        "opentelemetry.instrumentation.sqlalchemy.SQLAlchemyInstrumentor"
    ) as mock_sqlalchemy:
        setup_otel(None)

    mock_sqlalchemy.assert_not_called()


def test_setup_otel_instruments_sqlalchemy_without_fastapi_app(monkeypatch):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")

    with (
        patch(_EXPORTER_PATCHES[0]),
        patch(_EXPORTER_PATCHES[1]),
        patch("opentelemetry.instrumentation.sqlalchemy.SQLAlchemyInstrumentor") as mock_sqlalchemy,
        patch("opentelemetry.instrumentation.fastapi.FastAPIInstrumentor") as mock_fastapi,
        patch("app.db.session.engine"),
    ):
        setup_otel(None)

        mock_sqlalchemy.return_value.instrument.assert_called_once()
        mock_fastapi.instrument_app.assert_not_called()


def test_setup_otel_instruments_both_with_fastapi_app(monkeypatch):
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    app = FastAPI()

    with (
        patch(_EXPORTER_PATCHES[0]),
        patch(_EXPORTER_PATCHES[1]),
        patch("opentelemetry.instrumentation.sqlalchemy.SQLAlchemyInstrumentor") as mock_sqlalchemy,
        patch("opentelemetry.instrumentation.fastapi.FastAPIInstrumentor") as mock_fastapi,
        patch("app.db.session.engine"),
    ):
        setup_otel(app)

        mock_sqlalchemy.return_value.instrument.assert_called_once()
        mock_fastapi.instrument_app.assert_called_once_with(app)
