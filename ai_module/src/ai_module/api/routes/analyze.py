"""Analyze route — orchestrates the full AI analysis pipeline."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request, UploadFile

from ai_module.adapters.base import LLMAdapter
from ai_module.adapters.factory import get_llm_adapter
from ai_module.core.logger import get_logger
from ai_module.core.pipeline import run_pipeline
from ai_module.core.settings import settings
from ai_module.models.report import AnalyzeResponse

router = APIRouter()

logger = get_logger(__name__, level=settings.LOG_LEVEL)


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(
    request: Request,
    file: UploadFile,
    analysis_id: Annotated[str, Form(...)],
    adapter: Annotated[LLMAdapter, Depends(get_llm_adapter)],
    context_text: Annotated[
        str | None,
        Form(max_length=settings.CONTEXT_TEXT_MAX_LENGTH),
    ] = None,
) -> AnalyzeResponse:
    """Executa o pipeline completo de análise de IA para um arquivo enviado."""
    request.state.analysis_id = analysis_id
    file_bytes = await file.read()
    logger.info(
        "Solicitação de análise recebida",
        extra={
            "event": "analyze_request_received",
            "analysis_id": analysis_id,
            "details": {
                "filename": file.filename,
                "content_type": file.content_type,
                "file_size_bytes": len(file_bytes),
                "context_text_provided": bool(context_text),
                "context_text_length": len(context_text or ""),
                "app_version": settings.APP_VERSION,
                "llm_provider": settings.LLM_PROVIDER,
            },
        },
    )
    return await run_pipeline(
        file_bytes=file_bytes,
        filename=file.filename,  # type: ignore
        analysis_id=analysis_id,
        context_text=context_text,
        adapter=adapter,
    )
