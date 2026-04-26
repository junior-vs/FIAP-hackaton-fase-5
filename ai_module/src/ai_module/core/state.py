"""Service health state shared between main.py and routes.py."""

from __future__ import annotations

_service_healthy: bool = False


def set_service_health(value: bool) -> None:
    global _service_healthy
    _service_healthy = value
