import json
import logging

from deadair.logs import JsonFormatter


def test_json_log_lines_parse():
    rec = logging.LogRecord(
        "deadair.station", logging.INFO, __file__, 1, "block %s done", ("b1",), None
    )
    line = json.loads(JsonFormatter().format(rec))
    assert line["msg"] == "block b1 done" and line["logger"] == "deadair.station"
    assert line["level"] == "INFO" and line["ts"].endswith("+00:00")
