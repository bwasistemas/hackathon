import logging
import os
import sys

from pythonjsonlogger import jsonlogger


class _ServiceFormatter(jsonlogger.JsonFormatter):
    def __init__(self, service_name: str, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._service = service_name

    def add_fields(self, log_record, record, message_dict):
        super().add_fields(log_record, record, message_dict)
        log_record["service"] = self._service
        log_record["level"] = record.levelname
        log_record.pop("levelname", None)


def setup_logging(service_name: str) -> None:
    level = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(
        _ServiceFormatter(
            service_name,
            fmt="%(asctime)s %(levelname)s %(name)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    )
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
