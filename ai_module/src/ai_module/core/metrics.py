"""In-memory metrics counters for observability."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Metrics:
    """Contadores de requisições e tempos agregados para exportação Prometheus."""

    requests_success: int = 0
    requests_error: int = 0
    processing_time_ms_total: int = 0
    llm_retries_total: int = 0


metrics = Metrics()
