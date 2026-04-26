"""Health check route — returns service liveness and configuration."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from ai_module.core import state as _state
from ai_module.core.settings import settings

router = APIRouter()


@router.get("/health")
async def health_check() -> dict[str, Any]:
    """Retorna status de saúde do serviço.

    HTTP 200 quando o serviço está saudável; HTTP 503 quando degradado.
    """
    if not _state._service_healthy:
        raise HTTPException(
            status_code=503,
            detail={
                "status": "degraded",
                "version": settings.APP_VERSION,
                "llm_provider": settings.LLM_PROVIDER,
            },
        )
    return {
        "status": "healthy",
        "version": settings.APP_VERSION,
        "llm_provider": settings.LLM_PROVIDER,
    }
