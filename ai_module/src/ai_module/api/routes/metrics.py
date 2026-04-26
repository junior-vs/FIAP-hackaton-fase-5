"""Metrics route — exposes Prometheus-formatted counters and gauges."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import PlainTextResponse

from ai_module.core.logger import get_logger
from ai_module.core.metrics import metrics as _metrics
from ai_module.core.settings import settings

router = APIRouter()

logger = get_logger(__name__, level=settings.LOG_LEVEL)


@router.get("/metrics", response_class=PlainTextResponse)
def metrics_endpoint() -> str:
    """Endpoint de métricas que retorna no formato Prometheus."""
    logger.debug(
        "Received metrics request",
        extra={
            "details": {
                "app_version": settings.APP_VERSION,
                "llm_provider": settings.LLM_PROVIDER,
            }
        },
    )
    total_requests = _metrics.requests_success + _metrics.requests_error
    avg_ms = int(_metrics.processing_time_ms_total / total_requests) if total_requests else 0
    lines = [
        "# HELP ai_requests_total Total de solicitações de análise",
        "# TYPE ai_requests_total counter",
        f'ai_requests_total{{status="success"}} {_metrics.requests_success}',
        f'ai_requests_total{{status="error"}} {_metrics.requests_error}',
        "# HELP ai_processing_time_ms_avg Tempo médio de processamento em milissegundos",
        "# TYPE ai_processing_time_ms_avg gauge",
        f"ai_processing_time_ms_avg {avg_ms}",
        "# HELP ai_llm_retries_total Total de tentativas de retry do LLM",
        "# TYPE ai_llm_retries_total counter",
        f"ai_llm_retries_total {_metrics.llm_retries_total}",
        "# HELP ai_llm_provider_active Provedor LLM ativo (1=ativo)",
        "# TYPE ai_llm_provider_active gauge",
        f'ai_llm_provider_active{{provider="{settings.LLM_PROVIDER}"}} 1',
    ]
    return "\n".join(lines) + "\n"
