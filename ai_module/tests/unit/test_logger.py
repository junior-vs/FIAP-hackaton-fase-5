from __future__ import annotations

import logging

from ai_module.core.logger import get_logger


def _reset_logger(name: str) -> None:
    logger = logging.getLogger(name)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    logger.setLevel(logging.NOTSET)


def test_get_logger_updates_level_on_second_call() -> None:
    logger_name = "ai_module.tests.logger.level_update"
    _reset_logger(logger_name)

    logger = get_logger(logger_name, level="INFO")
    initial_handlers = len(logger.handlers)

    same_logger = get_logger(logger_name, level="ERROR")

    assert same_logger is logger
    assert len(logger.handlers) == initial_handlers
    assert logger.level == logging.ERROR
    assert all(handler.level == logging.ERROR for handler in logger.handlers)


def test_get_logger_invalid_level_falls_back_to_info() -> None:
    logger_name = "ai_module.tests.logger.invalid_level"
    _reset_logger(logger_name)

    logger = get_logger(logger_name, level="INVALID_LEVEL")

    assert logger.level == logging.INFO
    assert all(handler.level == logging.INFO for handler in logger.handlers)
