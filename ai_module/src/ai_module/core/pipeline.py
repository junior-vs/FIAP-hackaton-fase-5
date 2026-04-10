"""AI analysis pipeline orchestrating preprocessing, LLM calls, and validation."""

from __future__ import annotations

import time

from ai_module.adapters.base import LLMAdapter
from ai_module.core.exceptions import (
    AIFailureError,
    InvalidInputError,
    LLMCallError,
    LLMTimeoutError,
    UnsupportedFormatError,
)
from ai_module.core.logger import get_logger
from ai_module.core.metrics import metrics
from ai_module.core.preprocessor import preprocess
from ai_module.core.prompt_builder import (
    build_correction_prompt,
    build_system_prompt,
    build_user_prompt,
)
from ai_module.core.report_validator import validate_and_normalize
from ai_module.core.settings import settings
from ai_module.models.report import AnalyzeResponse, Report, ReportMetadata

logger = get_logger(__name__, level=settings.LOG_LEVEL)


def _truncate_for_log(value: str, limit: int = 500) -> str:
    compact_value = value.replace("\n", "\\n").replace("\r", "\\r")
    if len(compact_value) <= limit:
        return compact_value
    return compact_value[:limit] + "..."


def _file_signature_hex(file_bytes: bytes, limit: int = 16) -> str:
    return file_bytes[:limit].hex()


async def run_pipeline(
    file_bytes: bytes,
    filename: str,
    analysis_id: str,
    adapter: LLMAdapter,
) -> AnalyzeResponse:
    logger.info(
        "Analysis request received",
        extra={
            "event": "request_received",
            "analysis_id": analysis_id,
            "details": {
                "filename": filename,
                "file_size_bytes": len(file_bytes),
                "provider": settings.LLM_PROVIDER,
                "model": settings.LLM_MODEL,
            },
        },
    )
    total_start = time.monotonic()

    # ── Step 1: Preprocessing ─────────────────────────────────────────────────
    logger.info(
        "Preprocessing started",
        extra={
            "event": "preprocessing_start",
            "analysis_id": analysis_id,
            "details": {"filename": filename},
        },
    )
    pre_start = time.monotonic()
    try:
        image_bytes, input_type = preprocess(file_bytes, filename)
    except (UnsupportedFormatError, InvalidInputError) as e:
        logger.error(
            "Preprocessing failed",
            extra={
                "event": "preprocessing_error",
                "analysis_id": analysis_id,
                "details": {
                    "error_code": type(e).__name__,
                    "message": e.message,
                    "filename": filename,
                    "file_size_bytes": len(file_bytes),
                    "file_signature_hex": _file_signature_hex(file_bytes),
                },
            },
        )
        raise

    pre_ms = int((time.monotonic() - pre_start) * 1000)
    logger.info(
        "Preprocessing completed",
        extra={
            "event": "preprocessing_success",
            "analysis_id": analysis_id,
            "details": {
                "processing_time_ms": pre_ms,
                "input_type": input_type,
                "normalized_image_size_bytes": len(image_bytes),
            },
        },
    )

    # ── Step 2: Build prompts ────────────────────────────────────────────────
    system_prompt = build_system_prompt()
    user_prompt, _ = build_user_prompt(image_bytes)
    current_prompt = user_prompt
    logger.info(
        "Prompts built",
        extra={
            "event": "prompt_build_success",
            "analysis_id": analysis_id,
            "details": {
                "system_prompt_length": len(system_prompt),
                "user_prompt_length": len(user_prompt),
            },
        },
    )

    # ── Steps 3+4: LLM call with retry ───────────────────────────────────────
    report: Report | None = None
    provider = settings.LLM_PROVIDER.upper()
    last_raw: str = ""
    last_error: str = ""

    for attempt in range(1, settings.LLM_MAX_RETRIES + 1):
        # On retry after a validation failure, send a targeted correction prompt
        if attempt > 1 and last_raw and last_error:
            current_prompt = build_correction_prompt(last_raw, last_error)
            logger.info(
                "Prepared correction prompt",
                extra={
                    "event": "correction_prompt_built",
                    "analysis_id": analysis_id,
                    "details": {
                        "attempt": attempt,
                        "previous_error": _truncate_for_log(last_error, limit=300),
                    },
                },
            )

        logger.info(
            "LLM call started",
            extra={
                "event": "llm_call_start",
                "analysis_id": analysis_id,
                "details": {
                    "attempt": attempt,
                    "provider": provider,
                    "model": settings.LLM_MODEL,
                    "image_size_bytes": len(image_bytes),
                },
            },
        )
        llm_start = time.monotonic()

        try:
            raw = await adapter.analyze(image_bytes, current_prompt, system_prompt)
        except LLMTimeoutError as e:
            logger.warning(
                "LLM call timed out",
                extra={
                    "event": "llm_call_timeout",
                    "analysis_id": analysis_id,
                    "details": {
                        "attempt": attempt,
                        "timeout_seconds": settings.LLM_TIMEOUT_SECONDS,
                        "message": e.message,
                    },
                },
            )
            continue
        except LLMCallError as e:
            logger.error(
                "LLM call failed",
                extra={
                    "event": "llm_call_error",
                    "analysis_id": analysis_id,
                    "details": {
                        "attempt": attempt,
                        "error_type": type(e).__name__,
                        "message": e.message,
                    },
                },
            )
            continue

        llm_ms = int((time.monotonic() - llm_start) * 1000)
        logger.info(
            "LLM call succeeded",
            extra={
                "event": "llm_call_success",
                "analysis_id": analysis_id,
                "details": {
                    "attempt": attempt,
                    "processing_time_ms": llm_ms,
                    "model_used": settings.LLM_MODEL,
                    "raw_response_length": len(raw),
                },
            },
        )

        try:
            report, metadata_flags = validate_and_normalize(raw)
        except ValueError as e:
            last_raw = raw
            last_error = str(e)
            logger.warning(
                "Validation failed for LLM response",
                extra={
                    "event": "validation_error",
                    "analysis_id": analysis_id,
                    "details": {
                        "attempt": attempt,
                        "error": _truncate_for_log(last_error, limit=300),
                        "raw_response_excerpt": _truncate_for_log(raw),
                    },
                },
            )
            continue

        logger.info(
            "Report validation succeeded",
            extra={
                "event": "validation_success",
                "analysis_id": analysis_id,
                "details": {
                    "attempt": attempt,
                    "summary_truncated": metadata_flags["summary_truncated"],
                    "components_count": len(report.components),
                    "risks_count": len(report.risks),
                    "recommendations_count": len(report.recommendations),
                },
            },
        )

        metrics.requests_success += 1
        metrics.llm_retries_total += attempt - 1
        break

    if report is None:
        logger.error(
            "Analysis failed after all retries",
            extra={
                "event": "analysis_failure",
                "analysis_id": analysis_id,
                "details": {
                    "error_code": "AI_FAILURE",
                    "provider": provider,
                    "model": settings.LLM_MODEL,
                    "last_error": _truncate_for_log(last_error, limit=300) if last_error else None,
                    "last_raw_response_excerpt": _truncate_for_log(last_raw) if last_raw else None,
                },
            },
        )
        metrics.requests_error += 1
        raise AIFailureError("Failed to generate a valid report after all retries.")

    total_ms = int((time.monotonic() - total_start) * 1000)
    metrics.processing_time_ms_total += total_ms
    logger.info(
        "Analysis completed successfully",
        extra={
            "event": "analysis_success",
            "analysis_id": analysis_id,
            "details": {
                "total_time_ms": total_ms,
                "input_type": input_type,
            },
        },
    )

    return AnalyzeResponse(
        analysis_id=analysis_id,
        status="success",
        report=report,
        metadata=ReportMetadata(
            model_used=settings.LLM_MODEL,
            processing_time_ms=total_ms,
            input_type=input_type,  # type: ignore[arg-type]
        ),
    )