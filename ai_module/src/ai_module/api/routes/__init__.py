"""API routes package — assembles health, metrics, and analyze routers."""

from __future__ import annotations

from fastapi import APIRouter

from ai_module.api.routes.analyze import router as analyze_router
from ai_module.api.routes.health import router as health_router
from ai_module.api.routes.metrics import router as metrics_router

router = APIRouter()
router.include_router(health_router)
router.include_router(metrics_router)
router.include_router(analyze_router)

__all__ = ["router"]
