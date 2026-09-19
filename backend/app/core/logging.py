import json
import logging
from contextvars import ContextVar
from datetime import datetime, timezone
from uuid import UUID

# Set once per request by the route; every log line written while handling
# that request picks it up, so it doesn't have to be passed into each call.
session_id_var: ContextVar[str | None] = ContextVar("session_id", default=None)

_RESERVED = set(logging.makeLogRecord({}).__dict__) | {"message", "asctime"}


def bind_session(session_id: UUID) -> None:
    session_id_var.set(str(session_id))


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry = {
            "time": datetime.fromtimestamp(record.created, timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "session_id": record.session_id,
        }
        entry.update({k: v for k, v in record.__dict__.items() if k not in _RESERVED and k not in entry})
        if record.exc_info:
            entry["exception"] = self.formatException(record.exc_info)
        return json.dumps(entry, default=str)


def _install_record_factory() -> None:
    previous = logging.getLogRecordFactory()
    if getattr(previous, "adds_session_id", False):
        return

    # A record factory (not a handler filter) so the field is on every record,
    # whichever handler ends up formatting it.
    def factory(*args, **kwargs):
        record = previous(*args, **kwargs)
        record.session_id = session_id_var.get()
        return record

    factory.adds_session_id = True
    logging.setLogRecordFactory(factory)


def setup_logging() -> None:
    _install_record_factory()
    root = logging.getLogger()
    # Only replace our own handler, so handlers added by other tools (pytest's capture) survive.
    root.handlers = [h for h in root.handlers if not getattr(h, "is_json_handler", False)]
    handler = logging.StreamHandler()
    handler.is_json_handler = True
    handler.setFormatter(JsonFormatter())
    root.addHandler(handler)
    root.setLevel(logging.INFO)
    # httpx logs every outgoing request at INFO, which drowns out our own events.
    logging.getLogger("httpx").setLevel(logging.WARNING)
