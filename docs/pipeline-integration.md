# Pipeline Integration Analysis

**Purpose**: Document existing pipeline architecture for FUN-009 RabbitMQ consumer integration  
**Created**: 2026-05-01  
**Status**: Phase 0 Research Complete

## Executive Summary

The existing pipeline in `core/pipeline.py` is **ready for worker integration** without modification. It is:
- ✅ Stateless and adapter-based (PAT-004 compliant)
- ✅ Accepts all required inputs for queue messages
- ✅ Returns structured response objects
- ✅ Raises well-defined exceptions
- ✅ Fully instrumented with metrics and structured logging

## Pipeline Function Signature

```python
async def run_pipeline(
    file_bytes: bytes,
    filename: str,
    analysis_id: str,
    adapter: LLMAdapter,
    context_text: str | None = None,
) -> AnalyzeResponse
```

### Input Requirements

| Parameter | Type | Required | Description | Queue Message Mapping |
|-----------|------|----------|-------------|----------------------|
| `file_bytes` | `bytes` | Yes | Raw file content | Decoded from `file_bytes_b64` |
| `filename` | `str` | Yes | Original filename | From `file_name` field |
| `analysis_id` | `str` | Yes | UUID4 identifier | From `analysis_id` field |
| `adapter` | `LLMAdapter` | Yes | LLM provider adapter | Injected by worker (Gemini/OpenAI) |
| `context_text` | `str \| None` | No | Optional user context | From `context_text` field (nullable) |

### Output Structure

Returns `AnalyzeResponse` (Pydantic model):

```python
class AnalyzeResponse(BaseModel):
    analysis_id: str
    status: Literal["success"]
    report: Report
    metadata: ReportMetadata

class Report(BaseModel):
    summary: str
    components: list[Component]
    risks: list[Risk]
    recommendations: list[Recommendation]

class ReportMetadata(BaseModel):
    model_used: str
    processing_time_ms: int
    input_type: str
    context_text_provided: bool
    context_text_length: int
    conflict_detected: bool
    conflict_decision: str
    conflict_policy: str
```

## Exception Hierarchy

The pipeline raises **4 exception types** that must be mapped to queue error responses:

| Exception | Trigger | Error Code | Description | Queue Handling |
|-----------|---------|------------|-------------|----------------|
| `UnsupportedFormatError` | Invalid file format (not PNG/JPG/PDF) | `UNSUPPORTED_FORMAT` | File cannot be processed | Reject to DLQ (ERR-004) |
| `InvalidInputError` | Malformed file data | `INVALID_INPUT` | File is corrupted or unreadable | Reject to DLQ (ERR-004) |
| `AITimeoutError` | LLM timeout (>30s) | `AI_TIMEOUT` | LLM did not respond in time | Publish error result |
| `AIFailureError` | LLM validation failure after retries | `AI_FAILURE` | LLM output invalid after all attempts | Publish error result |

**Additional exceptions** (from adapters/preprocessor):
- `LLMCallError` (network/API failure) → wraps into `AIFailureError`
- `LLMTimeoutError` (explicit timeout) → wraps into `AITimeoutError`

### Exception Handling Strategy for Worker

```python
# Pseudo-code for worker exception mapping
try:
    response = await run_pipeline(...)
    await publish_success(response)
    await message.ack()

except (UnsupportedFormatError, InvalidInputError) as e:
    # Malformed input → reject to DLQ (no retry)
    logger.error("Invalid input, rejecting to DLQ", error=str(e))
    await message.reject(requeue=False)

except (AITimeoutError, AIFailureError) as e:
    # AI failure → publish error result, ACK message
    await publish_error(analysis_id, e.error_code, str(e))
    await message.ack()

except Exception as e:
    # Unexpected error → NACK for retry
    logger.error("Unexpected error, requeueing", error=str(e))
    await message.nack(requeue=True)
```

## Pipeline Internal Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                        run_pipeline()                           │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 1. Preprocessing (_step_preprocess)                            │
│    - Validate file format (PNG/JPG/PDF)                        │
│    - Convert to PNG if needed                                  │
│    - Raises: UnsupportedFormatError, InvalidInputError         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. Prompt Building (_step_build_prompts)                       │
│    - Build system prompt (role definition)                     │
│    - Build user prompt (image + context)                       │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3. LLM Retry Loop (_step_retry_loop)                           │
│    - Max 3 attempts with correction prompts                    │
│    - Timeout: 30s per attempt                                  │
│    - Validates JSON schema on each response                    │
│    - Raises: AIFailureError, AITimeoutError                    │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 4. Conflict Detection (_detect_conflict)                       │
│    - Compare context vs diagram if enabled                     │
│    - Policy: DIAGRAM_FIRST (spec SEC-002)                      │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 5. Response Assembly (_build_response)                         │
│    - Construct AnalyzeResponse with Report + Metadata          │
│    - Update metrics (success, timing, retries)                 │
└─────────────────────────────────────────────────────────────────┘
```

## Metrics Instrumentation

The pipeline **automatically updates global metrics**:

| Metric | Updated By | Description |
|--------|-----------|-------------|
| `metrics.requests_success` | `run_pipeline()` | Successful completions |
| `metrics.llm_retries_total` | `run_pipeline()` | Retry attempts used |
| `metrics.processing_time_ms_total` | `run_pipeline()` | Total processing time |
| `metrics.preprocessing_time_ms` | `_step_preprocess()` | Preprocessing duration |
| `metrics.llm_time_ms` | `_step_retry_loop()` | LLM call duration |

**Worker implications**: No additional metric collection needed in consumer - pipeline handles it automatically.

## Structured Logging

The pipeline emits structured logs (JSON format) at these events:

| Event | Log Level | Fields |
|-------|-----------|--------|
| `request_received` | INFO | analysis_id, filename, file_size, context_provided |
| `preprocessing_complete` | INFO | analysis_id, input_type, preprocessing_time_ms |
| `llm_call_start` | INFO | analysis_id, attempt, model |
| `llm_call_success` | INFO | analysis_id, attempt, tokens_used |
| `llm_call_failure` | WARNING | analysis_id, attempt, error |
| `conflict_detected` | WARNING | analysis_id, conflict_decision |
| `analysis_success` | INFO | analysis_id, total_time_ms |

**Worker implications**: Worker should log queue-specific events (message received, publish success/failure), pipeline logs internal events.

## Adapter Requirements

The pipeline requires an `LLMAdapter` instance. Current implementations:

| Adapter | Location | Model Support |
|---------|----------|---------------|
| `GeminiAdapter` | `adapters/gemini_adapter.py` | Gemini 1.5 Pro, 1.5 Flash |
| `OpenAIAdapter` | `adapters/openai_adapter.py` | GPT-4 Vision models |

**Worker integration**: Adapter must be resolved and injected by worker based on `settings.LLM_PROVIDER`.

Example:
```python
# In worker startup
from ai_module.adapters.gemini_adapter import GeminiAdapter
from ai_module.core.settings import settings

if settings.LLM_PROVIDER == "gemini":
    adapter = GeminiAdapter(api_key=settings.GEMINI_API_KEY)
else:
    raise ValueError(f"Unsupported provider: {settings.LLM_PROVIDER}")
```

## Statelessness Verification

The pipeline is **fully stateless**:

✅ No class state or singletons  
✅ All inputs passed as parameters  
✅ No file system access during processing  
✅ No database connections  
✅ Thread-safe (uses async/await)  
✅ Can be called concurrently from multiple workers

**Concurrency safety**: The pipeline can handle multiple messages in parallel (each on its own asyncio task) without race conditions.

## Integration Checklist for Worker

- [ ] Decode base64 `file_bytes_b64` → `bytes`
- [ ] Extract `filename` from queue message
- [ ] Pass `analysis_id` from queue message
- [ ] Resolve and inject `LLMAdapter` based on settings
- [ ] Pass optional `context_text` if present
- [ ] Map exceptions to queue error responses
- [ ] Publish success results to `analysis.results`
- [ ] Publish error results to `analysis.results`
- [ ] Reject malformed messages to DLQ
- [ ] ACK message only after successful publish
- [ ] Log queue-specific events (message received, published)

## Validation of PAT-004 Compliance

**Requirement**: "Shared pipeline behavior MUST be reused without modification"

✅ **Verified**: The pipeline can be called from worker context with **zero modifications**:
- All inputs available from queue message
- All outputs usable for queue response
- Exception handling compatible with queue semantics
- Metrics and logging work as-is

**Conclusion**: Worker integration is a **pure orchestration layer** - no pipeline changes needed.

---

**Task**: TASK-001 ✅ Complete  
**Next**: TASK-002 - RabbitMQ Library Selection
