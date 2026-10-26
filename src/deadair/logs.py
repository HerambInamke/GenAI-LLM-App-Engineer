"""Logging setup. `DEADAIR_LOG_JSON=1` emits one JSON object per line (NFR-9, TRD T-10)."""

import json
import logging
import os
from datetime import UTC, datetime


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        out = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            out["exc"] = self.formatException(record.exc_info)
        return json.dumps(out, ensure_ascii=False)


def setup_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler()
    if os.environ.get("DEADAIR_LOG_JSON") == "1":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter("%(asctime)s %(name)s %(message)s"))
    logging.basicConfig(level=level, handlers=[handler], force=True)
