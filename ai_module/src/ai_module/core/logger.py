"""Structured logging configuration with JSON output."""

from __future__ import annotations

import logging
import sys
from typing import Any

from pythonjsonlogger.json import JsonFormatter as BaseJsonFormatter


class JsonFormatter(BaseJsonFormatter):
    """Formatador JSON personalizado que garante campos obrigatórios.

    Estende o JsonFormatter base para garantir a presença dos campos
    'event' e 'details' em cada registro de log.
    """

    def add_fields(
        self,
        log_data: dict[str, Any],
        record: logging.LogRecord,
        message_dict: dict[str, Any],
    ) -> None:
        """Add mandatory fields to log record.

        Parameters
        ----------
        log_data : dict[str, Any]
            The log record dict to be serialized.
        record : logging.LogRecord
            The original logging.LogRecord.
        message_dict : dict[str, Any]
            Extra fields from the log call.
        """
        super().add_fields(log_data, record, message_dict)

        # Guarantee mandatory top-level fields even if formatter input changes.
        if "event" not in log_data:
            log_data["event"] = record.getMessage()
        if "level" not in log_data:
            log_data["level"] = record.levelname
        if "timestamp" not in log_data:
            log_data["timestamp"] = self.formatTime(record, self.datefmt)
        if "analysis_id" not in log_data:
            log_data["analysis_id"] = None

        # Move all extra fields into 'details' if not already present
        if "details" not in log_data:
            details = {}
            reserved = {"timestamp", "level", "event", "name"}
            for key in list(log_data.keys()):
                if key not in reserved:
                    details[key] = log_data.pop(key)
            log_data["details"] = details

        log_data.pop("message", None)
        log_data.pop("msg", None)


def get_logger(name: str, level: str = "INFO") -> logging.Logger:
    """Create and configure a structured JSON logger.

    Parameters
    ----------
    name : str
        Logger name (typically __name__ from calling module).

    Returns
    -------
    logging.Logger
        Configured logger instance emitting JSON to stdout.

    Examples
    --------
    >>> logger = get_logger(__name__)
    >>> logger.info("User login", extra={"details": {"user_id": 123}})
    # Output: {"timestamp": "...", "level": "INFO", "event": "User login",
    #          "details": {"user_id": 123}}
    """
    logger = logging.getLogger(name)
    log_level = getattr(logging, level.upper(), logging.INFO)

    # Keep idempotence (no duplicate handlers) while allowing level updates
    # in repeated calls (useful for tests and runtime reconfiguration).
    if logger.handlers:
        logger.setLevel(log_level)
        for handler in logger.handlers:
            handler.setLevel(log_level)
        return logger

    logger.setLevel(log_level)

    console_handler = logging.StreamHandler(stream=sys.stdout)
    console_handler.setLevel(log_level)

    formatter = JsonFormatter(
        "%(asctime)s %(levelname)s %(name)s %(message)s",
        rename_fields={
            "asctime": "timestamp",
            "levelname": "level",
            "message": "event",
        },
    )
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    logger.propagate = False

    return logger
