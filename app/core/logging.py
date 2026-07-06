import logging
import sys
from contextvars import ContextVar

from pythonjsonlogger import jsonlogger

trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")


class TraceIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = trace_id_var.get()
        return True


def configure_json_logging() -> None:
    handler = logging.StreamHandler(sys.stderr)
    handler.addFilter(TraceIdFilter())
    formatter = jsonlogger.JsonFormatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s %(trace_id)s",
        rename_fields={"asctime": "timestamp", "levelname": "level"},
    )
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.handlers = [handler]
    root_logger.setLevel(logging.INFO)
