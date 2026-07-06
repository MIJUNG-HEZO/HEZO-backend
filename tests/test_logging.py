import json
import logging

from app.core.logging import TraceIdFilter, configure_json_logging, trace_id_var


def test_trace_id_filter_injects_current_context_value():
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname="", lineno=1,
        msg="hello", args=(), exc_info=None,
    )
    token = trace_id_var.set("abc123")
    try:
        TraceIdFilter().filter(record)
        assert record.trace_id == "abc123"
    finally:
        trace_id_var.reset(token)


def test_trace_id_filter_defaults_to_empty_string():
    record = logging.LogRecord(
        name="test", level=logging.INFO, pathname="", lineno=1,
        msg="hello", args=(), exc_info=None,
    )
    TraceIdFilter().filter(record)
    assert record.trace_id == ""


def test_configure_json_logging_emits_json_with_trace_id(capsys):
    configure_json_logging()
    logger = logging.getLogger("test.json")
    token = trace_id_var.set("deadbeef")
    try:
        logger.info("hello world")
    finally:
        trace_id_var.reset(token)

    captured = capsys.readouterr()
    line = json.loads(captured.err.strip().splitlines()[-1])
    assert line["message"] == "hello world"
    assert line["trace_id"] == "deadbeef"
    assert "timestamp" in line
    assert line["level"] == "INFO"
