"""Service health state shared between main.py and routes.py."""

from __future__ import annotations

_service_healthy: bool = False
_queue_connected: bool = False


def set_service_health(value: bool) -> None:
    global _service_healthy
    _service_healthy = value


def set_queue_health(value: bool) -> None:
    global _queue_connected
    _queue_connected = value
