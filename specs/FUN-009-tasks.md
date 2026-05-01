# Implementation Plan: FUN-009 RabbitMQ Queue Consumer

**Feature**: FUN-009 - Consume asynchronous jobs from `analysis.requests`  
**Branch**: `main`  
**Date**: 2026-04-30  
**Spec**: [specs/spec.md](./spec.md)

## Summary

Implement a RabbitMQ consumer that processes architecture analysis requests from the `analysis.requests` queue, executes the shared analysis pipeline (PAT-004), and publishes results to `analysis.results`. This enables asynchronous analysis workflows alongside the existing synchronous HTTP API.

**Key Requirements**:

- Consume messages from `analysis.requests` queue
- Validate message schema before processing (ERR-004)
- Decode base64 file bytes and reuse existing pipeline
- Publish results to `analysis.results` queue
- Handle malformed messages → DLQ
- Add metrics and structured logging (OBS-004)
- Security boundary validation (SEC-002)

## Technical Context

**Language/Version**: Python 3.11  
**Primary Dependencies**: FastAPI 0.135.3, Pydantic 2.12.5, aio-pika (to be added)  
**Storage**: N/A (stateless service)  
**Testing**: pytest 9.0.2, pytest-asyncio 1.3.0  
**Target Platform**: Linux server (containerized)  
**Project Type**: Microservice (FastAPI + async worker)  
**Performance Goals**: Single-message prefetch, <30s processing per message  
**Constraints**:

- Reuse existing pipeline without modification
- Preserve layered architecture (api/core/adapters/models)
- No authentication within service
- Max file size: 10MB
- RabbitMQ connection must be resilient to network failures

**Scale/Scope**: Low-to-medium throughput async queue, 1-10 concurrent messages

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

✅ **Code Quality**:

- Preserve boundaries: adapters for RabbitMQ, core for pipeline logic, models for schemas
- Type hints required (Python 3.11)
- Reuse existing Pydantic models and pipeline
- Domain exceptions mapped to queue outcomes

✅ **Tests Define Done**:

- Unit tests for message validation, worker logic
- Integration tests for queue consumption/publication
- Contract tests for message schemas
- 80% coverage target maintained

✅ **Consumer Experience**:

- Queue contract matches spec exactly
- Error messages structured and actionable
- Observability via logs and metrics

✅ **Performance**:

- Single-message prefetch prevents overload
- Input validation before expensive processing
- Timeouts and retry limits enforced
- Fail-fast for malformed messages

**Violations**: None

## Project Structure

### Documentation (this feature)

```text
specs/
├── spec.md              # Main specification
└── FUN-009-tasks.md     # This file (implementation plan)
```

### Source Code (repository root)

```text
ai_module/
├── src/ai_module/
│   ├── adapters/
│   │   ├── base.py
│   │   ├── openai_adapter.py
│   │   ├── gemini_adapter.py
│   │   └── rabbitmq_adapter.py        # NEW: Queue connection adapter
│   ├── api/
│   │   └── routes/
│   │       ├── analyze.py
│   │       ├── health.py
│   │       └── metrics.py
│   ├── core/
│   │   ├── exceptions.py
│   │   ├── logger.py
│   │   ├── metrics.py
│   │   ├── pipeline.py                # EXISTING: Reused by worker
│   │   ├── preprocessor.py
│   │   ├── prompt_builder.py
│   │   ├── report_validator.py
│   │   ├── settings.py                # UPDATE: Add queue settings
│   │   └── state.py
│   ├── models/
│   │   ├── queue.py                   # NEW: Queue message schemas
│   │   └── report.py
│   ├── worker/
│   │   ├── __init__.py                # NEW: Worker module
│   │   ├── consumer.py                # NEW: Message consumer
│   │   └── publisher.py               # NEW: Result publisher
│   └── main.py                        # UPDATE: Start worker alongside FastAPI
└── tests/
    ├── contract/
    │   └── test_queue_contract.py     # NEW: Queue message contract tests
    ├── integration/
    │   └── test_worker_integration.py # NEW: End-to-end worker tests
    └── unit/
        ├── test_consumer.py           # NEW: Consumer unit tests
        ├── test_publisher.py          # NEW: Publisher unit tests
        └── test_queue_models.py       # NEW: Queue schema tests
```

**Structure Decision**:

- New `worker/` module for queue consumer/publisher logic (preserves boundary)
- New `adapters/rabbitmq_adapter.py` for connection management
- New `models/queue.py` for queue-specific Pydantic models
- Reuse existing `core/pipeline.py` without modification (PAT-004)

## Implementation Phases

### Phase 0: Architecture Review & Research

**Goal**: Understand existing pipeline, choose RabbitMQ library, define integration points

**Tasks**:

#### TASK-001: Review Existing Pipeline Architecture

- **Owner**: Developer
- **Effort**: 2 hours
- **Description**:
  - Read `core/pipeline.py` to understand `run_analysis()` function
  - Identify inputs required: `analysis_id`, `file_bytes`, `context_text`
  - Identify outputs: `AnalyzeResponse` model
  - Document exception types raised by pipeline
  - Verify pipeline is already adapter-based and stateless
- **Acceptance Criteria**:
  - Document created: `docs/pipeline-integration.md`
  - List of inputs, outputs, exceptions documented
  - Confirm pipeline can be called from worker context

#### TASK-002: RabbitMQ Library Selection

- **Owner**: Developer
- **Effort**: 2 hours
- **Description**:
  - Evaluate `aio-pika` (async) vs `pika` (sync)
  - Check compatibility with Python 3.11, asyncio, FastAPI lifecycle
  - Review connection resilience patterns
  - Make recommendation: `aio-pika` (async, better FastAPI integration)
- **Acceptance Criteria**:
  - Document decision in `docs/rabbitmq-library-choice.md`
  - Confirm `aio-pika` supports:
    - Async/await
    - Connection recovery
    - Prefetch control
    - Dead letter queue configuration

#### TASK-003: Define Worker Lifecycle Integration

- **Owner**: Developer
- **Effort**: 2 hours
- **Description**:
  - Review FastAPI lifespan events (`@asynccontextmanager`)
  - Plan how to start/stop RabbitMQ consumer alongside HTTP server
  - Define health check integration (degraded if queue fails)
  - Plan metrics integration (queue consumption, publication)
- **Acceptance Criteria**:
  - Document lifecycle in `docs/worker-lifecycle.md`
  - Confirm lifespan event pattern works with aio-pika
  - Define health check behavior for queue connectivity

**Phase 0 Deliverables**:

- ✅ `docs/pipeline-integration.md` (created)
- ✅ `docs/rabbitmq-library-choice.md` (created)
- ✅ `docs/worker-lifecycle.md` (created)

**Phase 0 Status**: ✅ **COMPLETE** (Completed: 2026-05-01)

**Phase 0 Summary**:
- Pipeline architecture analyzed and documented
- Library selected: `aio-pika>=9.0.0` for async RabbitMQ
- Lifecycle pattern defined: FastAPI lifespan with background task
- All inputs/outputs/exceptions mapped for worker integration
- Architecture verified as PAT-004 compliant (no pipeline modifications needed)

---

### Phase 1: Dependencies & Configuration

**Goal**: Add RabbitMQ library, extend settings, prepare infrastructure

**Tasks**:

#### TASK-004: Add aio-pika Dependency

- **Owner**: Developer
- **Effort**: 30 minutes
- **Status**: ✅ **COMPLETE** (Completed: 2026-05-01)
- **Description**:
  - Add `aio-pika` to `pyproject.toml` dependencies
  - Pin version (e.g., `aio-pika>=9.0.0,<10.0.0`)
  - Run `uv sync` to install
  - Verify mypy compatibility
- **Acceptance Criteria**:
  - ✅ `pyproject.toml` updated
  - ✅ Lock file regenerated
  - ✅ No mypy errors after installation

#### TASK-005: Extend Settings for RabbitMQ

- **Owner**: Developer
- **Effort**: 1 hour
- **Status**: ✅ **COMPLETE** (Completed: 2026-05-01)
- **Description**:
  - Verify existing RabbitMQ settings in `core/settings.py`:
    - `RABBITMQ_URL`, `RABBITMQ_INPUT_QUEUE`, `RABBITMQ_OUTPUT_QUEUE`
    - `RABBITMQ_EXCHANGE`, `RABBITMQ_PREFETCH_COUNT`
    - `RABBITMQ_RECONNECT_MAX_DELAY_SECONDS`
  - Add any missing settings
  - Add unit tests for settings validation
- **Acceptance Criteria**:
  - ✅ All RabbitMQ settings present and validated
  - ✅ Unit tests pass
  - ✅ Settings documented in `.env-exemplo`

**Phase 1 Deliverables**:

- ✅ Updated `pyproject.toml` (added `aio-pika>=9.0.0,<10.0.0`)
- ✅ Updated `core/settings.py` (normalized default values to match .env-exemplo)
- ✅ Verified `.env-exemplo` (already complete with all RabbitMQ settings)
- ✅ Unit tests added for RabbitMQ settings validation (9 new tests)
- ✅ Mypy compatibility verified (strict mode passes)

**Phase 1 Status**: ✅ **COMPLETE** (Completed: 2026-05-01)

**Phase 1 Summary**:
- aio-pika 9.6.2 installed successfully with dependencies (aiormq, pamqp, yarl, multidict, propcache)
- All RabbitMQ settings validated and tested (URL, queues, exchange, prefetch, reconnect delay)
- Type hints working with mypy strict mode (no issues found)
- Settings defaults aligned between settings.py and .env-exemplo
- Lock file regenerated with uv.lock

---

### Phase 2: Queue Message Models

**Goal**: Define Pydantic models for queue request/response messages

**Tasks**:

#### TASK-006: Create Queue Request Model

- **Owner**: Developer
- **Effort**: 1 hour
- **Status**: ✅ **COMPLETE** (Completed: 2026-05-01)
- **Description**:
  - Create `models/queue.py`
  - Define `QueueAnalysisRequest` model:

    ```python
    class QueueAnalysisRequest(BaseModel):
        analysis_id: str
        file_bytes_b64: str
        file_name: str
        context_text: str | None = None
    ```

  - Add validators:
    - `analysis_id`: non-empty string
    - `file_bytes_b64`: valid base64 string
    - `file_name`: non-empty string
    - `context_text`: max length 1000 if provided
  - Add method: `decode_file_bytes() -> bytes`
- **Acceptance Criteria**:
  - ✅ Model defined with strict validation
  - ✅ Decode method tested
  - ✅ Invalid base64 raises validation error
- **Implementation Summary**:
  - Created `models/queue.py` (5.9 KB) with full documentation
  - Implemented `QueueAnalysisRequest` with Pydantic v2 field_validator
  - Added 4 validators: analysis_id, file_bytes_b64, file_name, context_text
  - Implemented `decode_file_bytes()` method with error handling
  - Created 18 comprehensive unit tests (18/18 passing)
  - Mypy strict mode: 0 errors
  - Added `py.typed` marker for proper type checking

#### TASK-007: Create Queue Response Models

- **Owner**: Developer
- **Effort**: 1 hour
- **Status**: ✅ **COMPLETE** (Completed: 2026-05-01)
- **Description**:
  - Define `QueueAnalysisResponse` model (reuse `AnalyzeResponse` structure)
  - Define `QueueErrorResponse` model:

    ```python
    class QueueErrorResponse(BaseModel):
        analysis_id: str
        status: Literal["error"]
        error_code: str
        message: str
    ```

  - Ensure serialization to JSON works correctly
- **Acceptance Criteria**:
  - ✅ Models defined with correct field types
  - ✅ Serialization tested
  - ✅ Error codes match spec (INVALID_INPUT, AI_FAILURE, etc.)
- **Implementation Summary**:
  - Created `QueueAnalysisResponse` with Report and ReportMetadata integration
  - Created `QueueErrorResponse` with all required fields and validation
  - Added 15 comprehensive unit tests (33/33 total tests passing)
  - Mypy strict mode: 0 errors
  - Models mirror HTTP API response structure for consistency

#### TASK-008: Unit Tests for Queue Models

- **Owner**: Developer
- **Effort**: 2 hours
- **Status**: ✅ **COMPLETE** (Completed: 2026-05-01)
- **Description**:
  - Create `tests/unit/test_queue_models.py`
  - Test valid request parsing
  - Test invalid base64 rejection
  - Test context_text length validation
  - Test missing required fields
  - Test decode_file_bytes method
- **Acceptance Criteria**:
  - ✅ All model validation cases covered
  - ✅ 100% coverage for `models/queue.py`
- **Implementation Summary**:
  - Tests integrated with TASK-006 implementation
  - 18 comprehensive unit tests covering all scenarios
  - 100% test coverage on `models/queue.py`
  - All validators and edge cases tested

**Phase 2 Deliverables**:

- ✅ `models/queue.py` (Updated: 2026-05-01)
  - QueueAnalysisRequest model (from Phase 1)
  - QueueAnalysisResponse model (new)
  - QueueErrorResponse model (new)
- ✅ `tests/unit/test_queue_models.py` (Updated: 2026-05-01)
  - 33 comprehensive unit tests (33/33 passing)
  - 100% coverage on all queue models
- ✅ `py.typed` marker file (Created: 2026-05-01)

**Phase 2 Status**: ✅ **COMPLETE** (Completed: 2026-05-01)

**Phase 2 Summary**:
- ✅ TASK-006: **COMPLETE** (QueueAnalysisRequest with 4 validators and decode method)
- ✅ TASK-007: **COMPLETE** (QueueAnalysisResponse and QueueErrorResponse models)
- ✅ TASK-008: **COMPLETE** (33 comprehensive unit tests with 100% coverage)
- All models mirror HTTP API structure for consistency
- Type hints working with mypy strict mode (0 errors)
- JSON serialization validated for all models
- All spec error codes documented and tested

---

### Phase 3: RabbitMQ Adapter (Connection Management)

**Goal**: Create adapter for RabbitMQ connection lifecycle

**Tasks**:

#### TASK-009: Create RabbitMQ Adapter

- **Owner**: Developer
- **Status**: ✅ **COMPLETE** (Completed: 2026-05-01)
- **Effort**: 3 hours
- **Description**:
  - Create `adapters/rabbitmq_adapter.py`
  - Implement `RabbitMQAdapter` class:
    - `async def connect() -> None`
    - `async def disconnect() -> None`
    - `async def get_channel() -> aio_pika.Channel`
    - Connection recovery on failure
    - Exponential backoff (up to `RABBITMQ_RECONNECT_MAX_DELAY_SECONDS`)
  - Use settings for connection URL
  - Add structured logging for connection events
- **Acceptance Criteria**:
  - Connection established successfully
  - Reconnection logic tested (simulate disconnect)
  - Logs include connection status events

#### TASK-010: Unit Tests for RabbitMQ Adapter

- **Owner**: Developer
- **Status**: ✅ **COMPLETE** (Completed: 2026-05-01)
- **Effort**: 2 hours
- **Description**:
  - Create `tests/unit/test_rabbitmq_adapter.py`
  - Mock `aio_pika` for testing
  - Test successful connection
  - Test connection failure with retry
  - Test disconnect cleanup
- **Acceptance Criteria**:
  - All connection scenarios covered
  - No actual RabbitMQ connection in unit tests

**Phase 3 Deliverables**:

- ✅ `adapters/rabbitmq_adapter.py` (created)
- ✅ `tests/unit/test_rabbitmq_adapter.py` (created, 19 tests passing)

**Phase 3 Status**: ✅ **COMPLETE** (Completed: 2026-05-01)

**Phase 3 Summary**:
- `RabbitMQAdapter` with `connect()`, `disconnect()`, `get_channel()`, `is_connected`
- Exponential backoff retry capped at `RABBITMQ_RECONNECT_MAX_DELAY_SECONDS`
- `_safe_url()` helper strips AMQP credentials before logging
- `RabbitMQAdapter` exported from `adapters/__init__.py`
- 19 unit tests, all passing, zero real RabbitMQ dependency

---

### Phase 4: Consumer Implementation

**Goal**: Implement message consumer logic

**Tasks**:

#### TASK-011: [X] Create Message Consumer

- **Owner**: Developer
- **Effort**: 4 hours
- **Description**:
  - Create `worker/consumer.py`
  - Implement `MessageConsumer` class:
    - `async def start() -> None`: Start consuming messages
    - `async def stop() -> None`: Stop consumer gracefully
    - `async def _handle_message(message: aio_pika.IncomingMessage) -> None`
  - Message handling flow:
    1. Parse JSON → `QueueAnalysisRequest`
    2. Validate schema (ERR-004)
    3. Decode base64 file bytes
    4. Call `run_analysis()` pipeline (PAT-004)
    5. Publish result
    6. ACK message
    7. On validation error: NACK → DLQ
    8. On pipeline error: Publish error response, ACK
  - Set prefetch count from settings
  - Add structured logging for each step
  - Add metrics: messages_consumed, validation_errors, pipeline_errors
- **Acceptance Criteria**:
  - Consumer starts and stops cleanly
  - Valid messages processed successfully
  - Malformed JSON rejected to DLQ
  - Invalid base64 rejected to DLQ
  - Pipeline exceptions handled gracefully

#### TASK-012: [X] Unit Tests for Consumer

- **Owner**: Developer
- **Effort**: 3 hours
- **Description**:
  - Create `tests/unit/test_consumer.py`
  - Mock pipeline, publisher, RabbitMQ channel
  - Test valid message consumption
  - Test malformed JSON → NACK
  - Test invalid schema → NACK
  - Test pipeline exception → error response + ACK
  - Test base64 decode error → NACK
- **Acceptance Criteria**:
  - All consumer paths tested
  - No actual queue or pipeline calls

**Phase 4 Deliverables**:

- `worker/consumer.py`
- `tests/unit/test_consumer.py`

---

### Phase 5: Publisher Implementation

**Goal**: Implement result publisher logic

**Tasks**:

#### TASK-013: Create Result Publisher

- **Owner**: Developer
- **Effort**: 2 hours
- **Description**:
  - Create `worker/publisher.py`
  - Implement `ResultPublisher` class:
    - `async def publish_success(response: QueueAnalysisResponse) -> None`
    - `async def publish_error(error: QueueErrorResponse) -> None`
  - Publishing logic:
    - Serialize to JSON
    - Publish to `RABBITMQ_OUTPUT_QUEUE` with routing key `results`
    - Set message as persistent
    - Set content_type to `application/json`
  - Add retry logic (max 3 attempts)
  - Add structured logging
  - Add metrics: results_published, errors_published, publish_failures
- **Acceptance Criteria**:
  - Success messages published correctly
  - Error messages published correctly
  - Publish failures logged and retried

#### TASK-014: Unit Tests for Publisher

- **Owner**: Developer
- **Effort**: 2 hours
- **Description**:
  - Create `tests/unit/test_publisher.py`
  - Mock RabbitMQ channel
  - Test success message publishing
  - Test error message publishing
  - Test publish failure with retry
  - Test max retry exhaustion
- **Acceptance Criteria**:
  - All publisher paths tested
  - No actual queue connection

**Phase 5 Deliverables**:

- `worker/publisher.py`
- `tests/unit/test_publisher.py`

---

### Phase 6: Worker Lifecycle Integration

**Goal**: Integrate worker with FastAPI application lifecycle

**Tasks**:

#### TASK-015: Update Main Application

- **Owner**: Developer
- **Effort**: 3 hours
- **Description**:
  - Update `main.py`:
    - Add lifespan event handler (`@asynccontextmanager`)
    - Initialize RabbitMQ adapter, consumer, publisher
    - Start consumer in background task (`asyncio.create_task`)
    - Gracefully stop consumer on shutdown
  - Update health endpoint:
    - Add queue connectivity check
    - Return "degraded" if queue connection fails
  - Add metrics for queue connectivity
- **Acceptance Criteria**:
  - Worker starts with FastAPI app
  - Worker stops gracefully on app shutdown
  - Health check reflects queue status

#### TASK-016: Add Worker Metrics to Metrics Endpoint

- **Owner**: Developer
- **Effort**: 1 hour
- **Description**:
  - Extend `core/metrics.py` with queue metrics:
    - `queue_messages_consumed_total`
    - `queue_messages_published_total`
    - `queue_validation_errors_total`
    - `queue_pipeline_errors_total`
    - `queue_publish_failures_total`
  - Expose in `/metrics` endpoint
- **Acceptance Criteria**:
  - Metrics endpoint includes queue metrics
  - Prometheus format validated

**Phase 6 Deliverables**:

- Updated `main.py`
- Updated `core/metrics.py`
- Updated `api/routes/health.py`

---

### Phase 7: Integration Tests

**Goal**: Test end-to-end queue consumption and publication

**Tasks**:

#### TASK-017: Create Integration Test Suite

- **Owner**: Developer
- **Effort**: 4 hours
- **Description**:
  - Create `tests/integration/test_worker_integration.py`
  - Use real RabbitMQ instance (Docker for CI)
  - Test scenarios:
    1. Valid message → pipeline → success result published
    2. Malformed JSON → rejected to DLQ
    3. Invalid schema → rejected to DLQ
    4. Pipeline timeout → error result published
    5. Invalid file → error result published
  - Verify messages in output queue
  - Verify DLQ for rejected messages
- **Acceptance Criteria**:
  - All integration scenarios pass
  - Real queue used (not mocked)
  - Tests run in CI with Docker Compose

#### TASK-018: Docker Compose for Testing

- **Owner**: Developer
- **Effort**: 1 hour
- **Description**:
  - Create `docker-compose.test.yml` with RabbitMQ service
  - Configure DLQ for `analysis.requests`
  - Document how to run integration tests locally
- **Acceptance Criteria**:
  - RabbitMQ starts via Docker Compose
  - Integration tests pass with real queue

**Phase 7 Deliverables**:

- `tests/integration/test_worker_integration.py`
- `docker-compose.test.yml`

---

### Phase 8: Contract Tests

**Goal**: Ensure queue message schemas match specification exactly

**Tasks**:

#### TASK-019: Create Queue Contract Tests

- **Owner**: Developer
- **Effort**: 2 hours
- **Description**:
  - Create `tests/contract/test_queue_contract.py`
  - Test request message schema:
    - Required fields: `analysis_id`, `file_bytes_b64`, `file_name`
    - Optional field: `context_text`
    - Base64 validation
    - Context text length validation
  - Test response message schema:
    - Success: status, report, metadata
    - Error: status, error_code, message
  - Compare against spec examples
- **Acceptance Criteria**:
  - All contract tests pass
  - Schemas exactly match spec section 4.2

**Phase 8 Deliverables**:

- `tests/contract/test_queue_contract.py`

---

### Phase 9: Error Handling & Observability

**Goal**: Ensure proper error handling, logging, and metrics

**Tasks**:

#### TASK-020: Structured Logging for Worker

- **Owner**: Developer
- **Effort**: 2 hours
- **Description**:
  - Add structured logs for:
    - Message received (analysis_id, file_name)
    - Validation success/failure
    - Pipeline start/end
    - Result published
    - Errors and exceptions
  - Use existing `get_logger` with `extra` fields
  - Never log file bytes or raw binary data (SEC-003)
- **Acceptance Criteria**:
  - All worker operations logged
  - Logs include event names and analysis_id
  - No sensitive data in logs

#### TASK-021: Exception Handling Review

- **Owner**: Developer
- **Effort**: 2 hours
- **Description**:
  - Review all exception paths in consumer
  - Ensure domain exceptions mapped to queue error codes
  - Ensure unhandled exceptions don't crash worker
  - Add top-level exception handler in consumer
- **Acceptance Criteria**:
  - All exceptions handled gracefully
  - Worker remains running after errors
  - Error responses match spec error codes

**Phase 9 Deliverables**:

- Enhanced logging in `worker/consumer.py`
- Exception handling review complete

---

### Phase 10: Documentation

**Goal**: Document worker architecture, deployment, and operations

**Tasks**:

#### TASK-022: Update README

- **Owner**: Developer
- **Effort**: 1 hour
- **Description**:
  - Update `ai_module/README.md`:
    - Add RabbitMQ queue consumer section
    - Document queue message formats
    - Document environment variables for RabbitMQ
    - Add troubleshooting section
- **Acceptance Criteria**:
  - README includes worker documentation
  - Queue contracts documented
  - Operators can understand queue configuration

#### TASK-023: Create Worker Runbook

- **Owner**: Developer
- **Effort**: 2 hours
- **Description**:
  - Create `docs/worker-runbook.md`:
    - How to start worker
    - How to monitor queue health
    - How to handle DLQ messages
    - How to scale workers
    - Common issues and solutions
- **Acceptance Criteria**:
  - Runbook covers operational scenarios
  - Clear guidance for ops team

**Phase 10 Deliverables**:

- Updated `ai_module/README.md`
- `docs/worker-runbook.md`

---

### Phase 11: Validation & Quality Gates

**Goal**: Ensure all quality gates pass

**Tasks**:

#### TASK-024: Run Full Test Suite

- **Owner**: Developer
- **Effort**: 1 hour
- **Description**:
  - Run `pytest` with coverage
  - Verify 80%+ coverage maintained
  - Fix any failing tests
- **Acceptance Criteria**:
  - All tests pass
  - Coverage >= 80%

#### TASK-025: Run Static Analysis

- **Owner**: Developer
- **Effort**: 1 hour
- **Description**:
  - Run `ruff check` and `ruff format`
  - Run `mypy` in strict mode
  - Fix any type errors or lint issues
- **Acceptance Criteria**:
  - No ruff errors
  - No mypy errors

#### TASK-026: Manual Testing

- **Owner**: Developer
- **Effort**: 2 hours
- **Description**:
  - Start app with RabbitMQ locally
  - Publish test messages to `analysis.requests`
  - Verify results in `analysis.results`
  - Verify DLQ behavior for malformed messages
  - Check health endpoint
  - Check metrics endpoint
- **Acceptance Criteria**:
  - End-to-end flow works correctly
  - All observability signals present

**Phase 11 Deliverables**:

- All tests passing
- All quality gates green
- Manual validation complete

---

## Task Summary

| Phase | Tasks | Estimated Effort |
|-------|-------|------------------|
| Phase 0: Research | 3 tasks | 6 hours |
| Phase 1: Dependencies | 2 tasks | 1.5 hours |
| Phase 2: Models | 3 tasks | 4 hours |
| Phase 3: Adapter | 2 tasks | 5 hours |
| Phase 4: Consumer | 2 tasks | 7 hours |
| Phase 5: Publisher | 2 tasks | 4 hours |
| Phase 6: Lifecycle | 2 tasks | 4 hours |
| Phase 7: Integration | 2 tasks | 5 hours |
| Phase 8: Contracts | 1 task | 2 hours |
| Phase 9: Observability | 2 tasks | 4 hours |
| Phase 10: Docs | 2 tasks | 3 hours |
| Phase 11: Validation | 3 tasks | 4 hours |
| **Total** | **26 tasks** | **~49 hours** |

## Acceptance Criteria Checklist

### Functional

- [ ] AC-006: Valid queue message → pipeline execution → result published
- [ ] AC-007: Malformed queue JSON → rejected without pipeline call

### Technical

- [ ] PAT-004: Shared pipeline reused (no duplication)
- [ ] ERR-004: Malformed messages rejected to DLQ
- [ ] SEC-002: Request boundary validation for all inputs
- [ ] SEC-003: No file bytes, API keys, or context_text in logs

### Observability

- [ ] OBS-001: Structured logs with semantic events
- [ ] OBS-004: Queue outcomes observable in logs and metrics
- [ ] Health endpoint reflects queue connectivity
- [ ] Metrics endpoint includes queue metrics

### Quality

- [ ] All unit tests pass
- [ ] All integration tests pass
- [ ] All contract tests pass
- [ ] Coverage >= 80%
- [ ] No ruff errors
- [ ] No mypy errors

## Dependencies & Risks

### Dependencies

- **External**: RabbitMQ server must be running and accessible
- **Internal**: Existing pipeline (`core/pipeline.py`) must remain stable
- **Library**: `aio-pika` compatibility with Python 3.11 + FastAPI

### Risks

| Risk | Impact | Mitigation |
|------|--------|------------|
| Pipeline changes break worker | High | Integration tests catch breakage early |
| RabbitMQ connection instability | Medium | Connection recovery + exponential backoff |
| Base64 decoding memory issues | Medium | Validate file size before decode |
| DLQ messages accumulate | Low | Monitoring + manual DLQ review process |
| Worker crashes on unhandled exception | High | Top-level exception handler in consumer |

## Next Steps After Completion

1. **Deployment**:
   - Deploy worker alongside HTTP API
   - Configure RabbitMQ connection in production
   - Monitor queue metrics and health

2. **SOAT Integration**:
   - Coordinate flag day deployment with SOAT team
   - Run contract tests between services
   - Verify end-to-end flow in staging

3. **Monitoring**:
   - Set up alerts for queue depth
   - Set up alerts for DLQ accumulation
   - Set up alerts for worker health degradation

4. **Future Enhancements**:
   - FUN-010: Publish results to `analysis.results` (already covered here)
   - Add queue message tracing (correlation IDs)
   - Add queue performance metrics (processing time distribution)

## References

- Main Specification: [specs/spec.md](./spec.md)
- Constitution: [.specify/memory/constitution.md](../.specify/memory/constitution.md)
- Copilot Instructions: [.github/copilot/copilot-instructions.md](../.github/copilot/copilot-instructions.md)
- aio-pika Documentation: <https://aio-pika.readthedocs.io/>
