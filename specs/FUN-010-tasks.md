# Implementation Plan: FUN-010 - Publish Asynchronous Results to analysis.results

**Feature**: FUN-010 - RabbitMQ Result Publisher  
**Branch**: `main`  
**Date**: 2026-04-30  
**Spec**: specs/spec.md (FUN-010)

---

## Executive Summary

**Objective**: Implement a RabbitMQ publisher to send analysis results (both success and error) to the `analysis.results` queue, enabling asynchronous result delivery for the AI Module.

**Scope**: This implementation adds a result publishing capability that:
- Publishes both successful analysis reports and error results to RabbitMQ
- Ensures message durability and proper error handling
- Reuses existing pipeline results (PAT-004)
- Provides observability through structured logging and metrics (OBS-004)
- Surfaces publishing failures explicitly for retry (ERR-005)

**Related Requirements**:
- **FUN-010**: Publish async results to `analysis.results`
- **PAT-004**: Reuse shared pipeline behavior
- **ERR-005**: Surface publishing failures explicitly
- **DAT-003**: Report schema with summary, components, risks, recommendations
- **OBS-004**: Observable queue outcomes via logs and metrics

---

## Technical Context

**Language/Version**: Python 3.11  
**Primary Dependencies**: 
- FastAPI 0.135.3
- Pydantic 2.12.5
- RabbitMQ (via aio-pika or pika - TO BE DETERMINED)

**Storage**: RabbitMQ message queue (durable messages)  
**Testing**: pytest 9.0.2, pytest-asyncio 1.3.0, pytest-cov 7.1.0  
**Target Platform**: Linux server (async Python service)  
**Project Type**: Microservice with async messaging  
**Performance Goals**: Publish results within <100ms, handle connection failures gracefully  
**Constraints**: 
- Must maintain 80% test coverage
- Must preserve existing architecture boundaries
- Must not break HTTP flow

**Scale/Scope**: Single publisher instance, shared with RabbitMQ consumer (FUN-009)

---

## Constitution Check

### Pre-Design Gates

✅ **Code Quality**:
- New publisher will reside in `worker/` (consistent with FUN-009 consumer)
- RabbitMQ adapter in `adapters/` (shared with FUN-009, follows PAT-003)
- Type hints required for all new code (Python 3.11 compatible)
- Pydantic models already defined in `models/report.py`
- Domain exceptions in `worker/exceptions.py` (worker-specific)

✅ **Tests Define Done**:
- Unit tests required for publisher (success, error, connection failure scenarios)
- Integration tests required for end-to-end publishing
- Contract tests required to validate message schema

✅ **Consumer Experience**:
- Queue message contracts defined (success and error schemas)
- Error responses will include `error_code` and `message`
- No breaking changes to HTTP API

✅ **Performance**:
- Async publishing to avoid blocking pipeline
- Connection pooling if using aio-pika
- Publish timeout protection
- Explicit error handling for connection failures

### Post-Design Verification

Will re-evaluate after Phase 1 design artifacts are complete.

---

## Project Structure
  

---

## Implementation Phases

### Phase 0: Research & Decision Making

**Goal**: Resolve library choice and establish patterns

#### Tasks:

1. **Research async RabbitMQ libraries**
   - **Options**: `aio-pika` (async native), `pika` (sync with thread pool)
   - **Criteria**: Async-first, FastAPI compatible, connection pooling, error handling
   - **Decision point**: Document chosen library and rationale
   - **Output**: `FUN-010-research.md`

2. **Research connection management patterns**
   - Connection pooling vs single connection
   - Reconnection strategies
   - Graceful degradation (continue HTTP if RabbitMQ unavailable)
   - **Output**: Connection strategy section in research.md

3. **Research publish-or-fail patterns**
   - How to surface publish failures (ERR-005)
   - Should pipeline fail if publish fails?
   - Retry strategies (immediate vs deferred)
   - **Output**: Error handling strategy in research.md

4. **Research message durability**
   - Exchange declaration (durable, type=direct)
   - Queue declaration (durable, persistent messages)
   - Confirm mode for guaranteed delivery
   - **Output**: Durability strategy in research.md

**Definition of Done**:
- `FUN-010-research.md` complete with decisions on:
  - Library choice (aio-pika recommended)
  - Connection management approach
  - Publish failure handling
  - Message durability settings

---

### Phase 1: Design & Contracts

**Goal**: Define message schemas, publisher interface, and integration points

#### Tasks:

1. **Define message contracts** (`specs/FUN-010-contracts/`)
   - `success-result.json`: Success result schema with report
   - `error-result.json`: Error result schema with error_code
   - Validate against DAT-003 (summary, components, risks, recommendations)
   - **Output**: JSON schema files

2. **Design publisher interface** (`FUN-010-data-model.md`)
   - `ResultPublisher` class signature (in `worker/publisher.py`)
   - `publish_success(analysis_id, report, metadata)` method
   - `publish_error(analysis_id, error_code, message)` method
   - Uses `RabbitMQAdapter` for connection management (shared with FUN-009)
   - **Output**: Interface design in data-model.md

3. **Design integration points**
   - **Consumer orchestration**: Consumer calls pipeline → then publisher (not pipeline)
   - Where publisher is initialized (main.py via shared adapter)
   - How publisher failures are handled (exception types in `worker/exceptions.py`)
   - **Output**: Integration design in data-model.md

4. **Design publisher exceptions** (`worker/exceptions.py`)
   - `PublishError`: General publish failure
   - `PublishConnectionError`: RabbitMQ connection unavailable (raised by adapter)
   - `MessageSerializationError`: Failed to serialize result
   - **Note**: Connection exceptions from `adapters/rabbitmq_adapter.py` are wrapped
   - **Output**: Exception hierarchy in data-model.md

5. **Design metrics and logging**
   - Metrics: `publish_success_total`, `publish_error_total`, `publish_failure_total`, `publish_duration_seconds`
   - Logs: `result_published` (success), `publish_failed` (error)
   - **Output**: Observability design in data-model.md

6. **Create quickstart guide** (`FUN-010-quickstart.md`)
   - How to configure RabbitMQ connection
   - How to test publisher locally
   - How to monitor publishing
   - **Output**: Quickstart document

7. **Update agent context**
   - Run `.specify/scripts/powershell/update-agent-context.ps1 -AgentType copilot`
   - Add RabbitMQ publishing patterns to copilot instructions

**Definition of Done**:
- Message contracts defined and validated
- Publisher interface documented
- Integration points specified
- Exception hierarchy defined
- Observability plan documented
- Quickstart guide complete
- Agent context updated

---

### Phase 2: Implementation

**Goal**: Implement publisher, integrate with pipeline, ensure error handling

#### Tasks:

1. **Add RabbitMQ dependency**
   - Add `aio-pika>=9.0.0` to `pyproject.toml`
   - Run dependency installation
   - **Files**: `pyproject.toml`, `uv.lock`

2. **Verify RabbitMQ adapter exists** (`adapters/rabbitmq_adapter.py`)
   - Should already exist from FUN-009 implementation
   - Provides: `connect()`, `disconnect()`, `is_connected()`, `get_channel()`
   - Handles reconnection with exponential backoff
   - **Action**: Verify interface compatibility, extend if needed
   - **Files**: `ai_module/src/ai_module/adapters/rabbitmq_adapter.py`

3. **Implement publisher exceptions** (`worker/exceptions.py`)
   - Define `PublishError`, `PublishConnectionError`, `MessageSerializationError`
   - Import base `WorkerError` if defined (consistent with consumer)
   - **Files**: `ai_module/src/ai_module/worker/exceptions.py`

4. **Implement ResultPublisher class** (`worker/publisher.py`)
   - **Constructor**: Accept `RabbitMQAdapter` instance (dependency injection)
   - `publish_success()`: Serialize AnalyzeResponse, publish to queue
   - `publish_error()`: Serialize ErrorResponse, publish to queue
   - Exchange and queue declaration (durable, type=direct)
   - Error handling with explicit exceptions
   - Structured logging for publish events
   - Uses adapter for channel access (no direct connection management)
   - **Files**: `ai_module/src/ai_module/worker/publisher.py`

5. **Update metrics** (`core/metrics.py`)
   - Add `publish_success_total`, `publish_error_total`, `publish_failure_total`
   - Add `publish_duration_seconds` histogram
   - **Files**: `ai_module/src/ai_module/core/metrics.py`

6. **Initialize publisher in main** (`main.py`)
   - Create shared `RabbitMQAdapter` instance on startup
   - Pass adapter to both `Consumer` (FUN-009) and `Publisher` (FUN-010)
   - Gracefully handle adapter initialization failure
   - Close adapter connection on shutdown (shared lifecycle)
   - **Files**: `ai_module/src/ai_module/main.py`

**Definition of Done**:
- Dependency added and installed
- Publisher class implemented using shared adapter
- Metrics added for publish events
- Main app initializes publisher via shared adapter
- Publisher uses adapter for all RabbitMQ operations
- Type hints present, mypy clean
- No breaking changes to existing tests
- Pipeline remains UNCHANGED (pure business logic)

---

### Phase 3: Testing

**Goal**: Comprehensive test coverage for publisher and integration

#### Tasks:

1. **Unit test: Publisher success path** (`tests/unit/test_publisher.py`)
   - Test `publish_success()` with valid report
   - Mock aio-pika channel and exchange
   - Verify message serialization and publish call
   - Verify metrics increment

2. **Unit test: Publisher error path**
   - Test `publish_error()` with error details
   - Verify error message format
   - Verify metrics increment

3. **Unit test: Connection failure handling**
   - Test connection failure on `connect()`
   - Test reconnection with exponential backoff
   - Test publish failure when disconnected
   - Verify exceptions raised

4. **Unit test: Message serialization**
   - Test serialization of AnalyzeResponse
   - Test serialization of ErrorResponse
   - Test handling of non-serializable data

5. **Integration test: End-to-end publishing** (`tests/integration/test_rabbitmq_publish.py`)
   - Use real RabbitMQ (via docker-compose or testcontainers)
   - Run full pipeline with publisher enabled
   - Consume message from `analysis.results` queue
   - Verify message content matches expected schema

6. **Integration test: Consumer-Publisher flow** (`tests/integration/test_consumer_publisher.py`)
   - Verify consumer orchestrates: pipeline execution → result publishing
   - Test success path: valid message → pipeline → publish success
   - Test error path: pipeline error → publish error
   - Verify publisher NOT called from pipeline (separation verified)

7. **Contract test: Validate message schemas** (`tests/contract/test_result_contracts.py`)
   - Load contract JSON schemas
   - Validate success message against success-result.json
   - Validate error message against error-result.json
   - Verify required fields present

8. **Integration test: Shared adapter** (`tests/integration/test_shared_adapter.py`)
   - Verify consumer and publisher share single RabbitMQAdapter instance
   - Test concurrent operations (consume + publish)
   - Verify connection pooling works correctly

**Definition of Done**:
- All unit tests pass
- Integration tests pass (with real RabbitMQ)
- Contract tests validate schemas
- Coverage remains ≥80%
- No flaky tests

---

### Phase 4: Error Handling & Observability

**Goal**: Ensure robust error handling and observability (ERR-005, OBS-004)

#### Tasks:

1. **Implement explicit failure surfacing**
   - Ensure `PublishError` bubbles up to caller
   - Log publish failures with analysis_id, error details
   - Emit metric: `publish_failure_total` with labels (error_type)

2. **Add structured logging**
   - Log `result_published` with analysis_id, status, queue name
   - Log `publish_failed` with analysis_id, error, retry_count
   - Include RabbitMQ connection state in logs

3. **Add connection health check**
   - Implement `is_connected()` method
   - Expose health status in `/health` endpoint (if applicable)
   - Log connection state changes

4. **Test observability**
   - Verify logs emitted for success/error scenarios
   - Verify metrics incremented correctly
   - Verify Prometheus metrics endpoint includes new metrics

**Definition of Done**:
- Publish failures logged with full context
- Metrics exposed for Prometheus scraping
- Health check reflects publisher state
- Logs are structured and parseable

---

### Phase 5: Documentation & Validation

**Goal**: Complete documentation and validate implementation

#### Tasks:

1. **Update README** (`ai_module/README.md`)
   - Document RabbitMQ publisher feature
   - Add configuration section for RABBITMQ_* variables
   - Add troubleshooting guide for connection issues

2. **Document message schemas**
   - Add schema examples to documentation
   - Document error codes and their meanings
   - Document retry behavior

3. **Create runbook** (`docs/runbooks/rabbitmq-publisher.md`)
   - How to monitor publisher health
   - How to diagnose connection issues
   - How to handle publish failures
   - How to verify message delivery

4. **Validate against requirements**
   - ✅ FUN-010: Results published to `analysis.results`
   - ✅ PAT-004: Pipeline behavior reused (same Report object)
   - ✅ ERR-005: Publish failures surfaced explicitly
   - ✅ DAT-003: Report contains summary, components, risks, recommendations
   - ✅ OBS-004: Logs and metrics provide observability

5. **Run full quality gates**
   - `ruff check` (no violations)
   - `mypy` (strict, no errors)
   - `pytest --cov` (≥80% coverage)
   - Manual smoke test with real RabbitMQ

**Definition of Done**:
- Documentation complete and accurate
- All requirements validated
- Quality gates pass
- Feature ready for review

---

## Risk Assessment

### High Risk

1. **RabbitMQ dependency introduces new failure mode**
   - *Mitigation*: Make publisher optional, degrade gracefully if unavailable
   - *Mitigation*: Comprehensive connection failure handling and retries

2. **Message schema mismatch with consumer**
   - *Mitigation*: Contract tests validate schema compatibility
   - *Mitigation*: Use Pydantic models to ensure serialization correctness

### Medium Risk

1. **Performance impact of synchronous publishing**
   - *Mitigation*: Use async aio-pika library
   - *Mitigation*: Add timeout protection (<100ms)

2. **Test flakiness with RabbitMQ integration tests**
   - *Mitigation*: Use testcontainers or docker-compose for deterministic environment
   - *Mitigation*: Add retry logic to integration test setup

### Low Risk

1. **Breaking changes to existing HTTP flow**
   - *Mitigation*: Publisher is optional parameter, default=None preserves existing behavior
   - *Mitigation*: Existing tests will catch regressions

---

## Dependencies

### External Dependencies
- RabbitMQ server (local or remote)
- `aio-pika` library (to be added)

### Internal Dependencies
- **Depends on**: Existing pipeline (`core/pipeline.py`) - reuses result objects
- **Depends on**: Existing models (`models/report.py`) - AnalyzeResponse, ErrorResponse
- **Depends on**: RabbitMQ adapter (`adapters/rabbitmq_adapter.py`) - shared with FUN-009
- **Depends on**: FUN-009 consumer (`worker/consumer.py`) - consumer orchestrates publisher
- **Integrates with**: FUN-009 (shared adapter, message schemas, worker module)

---

## Rollout Plan

### Phase 1: Development
1. Implement on local branch
2. All tests pass locally
3. Code review by team

### Phase 2: Testing
1. Deploy to staging with RabbitMQ enabled
2. Verify messages published correctly
3. Monitor logs and metrics
4. Test failure scenarios (RabbitMQ down, network issues)

### Phase 3: Production
1. Enable publisher in production
2. Monitor publish success/failure rates
3. Set up alerts for publish failures
4. Document operational procedures

---

## Success Criteria

✅ **Functional**:
- Results published to `analysis.results` queue
- Success messages contain full report (summary, components, risks, recommendations)
- Error messages contain error_code and message
- Messages are durable and persistent

✅ **Quality**:
- Test coverage ≥80%
- All quality gates pass (ruff, mypy, pytest)
- No breaking changes to HTTP API

✅ **Observability**:
- Structured logs for publish events
- Metrics exposed for monitoring
- Publish failures surfaced explicitly

✅ **Performance**:
- Publishing completes in <100ms
- No degradation to HTTP response time
- Graceful handling of connection failures

---

## Design Decisions (Resolved)

1. **Where should publisher live?**
   - ✅ **Decision**: `worker/publisher.py` (consistent with FUN-009 consumer)
   - **Rationale**: Worker components handle async messaging, core remains pure business logic
   - **Follows**: PAT-001 (preserve boundaries)

2. **How to manage RabbitMQ connections?**
   - ✅ **Decision**: Shared `adapters/rabbitmq_adapter.py` with consumer (FUN-009)
   - **Rationale**: Single connection pool, consistent reconnection logic, follows PAT-003
   - **Benefit**: Reduced resource usage, simpler lifecycle management

3. **Should pipeline call publisher?**
   - ✅ **Decision**: NO - Consumer orchestrates both pipeline and publisher
   - **Rationale**: Pipeline stays pure (PAT-004), separation of concerns maintained
   - **Flow**: `Consumer → Pipeline → Consumer → Publisher`

4. **Should we use publisher confirm mode?**
   - ✅ **Decision**: YES, use confirm mode for guaranteed delivery
   - **Rationale**: Critical results must not be lost
   - **Trade-off**: Slight latency increase (<10ms) for reliability

5. **Should publisher be singleton or per-request?**
   - ✅ **Decision**: Singleton via shared adapter
   - **Rationale**: Connection reuse, consistent with adapter pattern

6. **What happens if publish fails?**
   - ✅ **Decision**: Raise exception, NACK message, trigger RabbitMQ retry
   - **Rationale**: Guarantees eventual delivery, aligns with queue semantics
   - **Monitoring**: Publish failures logged and metered (ERR-005)

---

## Next Steps

1. ✅ Complete this implementation plan
2. ⏳ Run Phase 0 research (library selection)
3. ⏳ Run Phase 1 design (contracts and interfaces)
4. ⏳ Execute Phase 2 implementation
5. ⏳ Execute Phase 3 testing
6. ⏳ Execute Phase 4 observability
7. ⏳ Execute Phase 5 documentation

---

## Alignment with FUN-009

**Critical**: This implementation MUST align with FUN-009 (Consumer) to ensure consistency.

### Shared Components

| Component | Location | Shared By | Purpose |
|-----------|----------|-----------|---------|
| RabbitMQ Adapter | `adapters/rabbitmq_adapter.py` | FUN-009, FUN-010 | Connection management, reconnection logic |
| Message Schemas | `specs/FUN-009-010-plan.md` | FUN-009, FUN-010 | Request/Result contract definitions |
| Worker Module | `worker/` | FUN-009, FUN-010 | Consumer and Publisher colocated |
| Metrics | `core/metrics.py` | FUN-009, FUN-010 | Queue operation observability |

### Architecture Consistency

```
┌────────────────────────────────────────────────────────────────┐
│                       RabbitMQ Broker                          │
│                                                                │
│  analysis.requests ──────────────▶ analysis.results           │
└────────────────────────────────────────────────────────────────┘
         │                                    ▲
         │ FUN-009 consume            FUN-010 publish
         │                                    │
         ▼                                    │
┌────────────────────────────────────────────────────────────────┐
│                     AI Module Service                          │
│                                                                │
│  ┌──────────────────┐         ┌──────────────────┐           │
│  │  HTTP Handler    │         │  Queue Worker    │           │
│  │  POST /analyze   │         │  (consumer.py)   │           │
│  └────────┬─────────┘         └────────┬─────────┘           │
│           │                            │                      │
│           │    Shared Adapter          │                      │
│           │    ┌─────────────────┐    │                      │
│           │    │ rabbitmq_adapter│◀───┘                      │
│           │    └─────────────────┘                           │
│           │            │                                      │
│           │            │                                      │
│           ▼            ▼                                      │
│  ┌──────────────────────────────┐                            │
│  │   Core Pipeline (PAT-004)    │                            │
│  │   - Decode                   │                            │
│  │   - Analyze (Gemini)         │                            │
│  │   - Generate Report          │                            │
│  └──────────────────────────────┘                            │
│           │                                                   │
│           │ (result object)                                   │
│           │                                                   │
│           ▼                                                   │
│  ┌──────────────────┐                                        │
│  │  Publisher       │                                        │
│  │  (publisher.py)  │                                        │
│  └────────┬─────────┘                                        │
│           │                                                   │
│           └──────────────────────────────▶ (via adapter)     │
└────────────────────────────────────────────────────────────────┘
```

### Key Alignment Points

1. **Module Structure**: Both in `worker/` module
2. **Adapter Sharing**: Single `RabbitMQAdapter` instance
3. **Exception Handling**: Consistent exception hierarchy in `worker/exceptions.py`
4. **Observability**: Metrics and logs use same patterns
5. **Pipeline Reuse**: Both use `core/pipeline.py` results (PAT-004)
6. **Testing Strategy**: Same approach (unit, integration, contract)

### Integration Flow (FUN-009 Consumer orchestrates FUN-010 Publisher)

```python
# Pseudo-code in consumer.py (FUN-009)
async def process_message(message: IncomingMessage):
    try:
        # 1. Validate and decode (FUN-009)
        request = validate_request(message.body)
        
        # 2. Run pipeline (PAT-004 - shared behavior)
        result = await run_pipeline(request.file_bytes, request.analysis_id)
        
        # 3. Publish success (FUN-010)
        await publisher.publish_success(
            analysis_id=request.analysis_id,
            report=result,
            metadata={"processing_time": elapsed}
        )
        
        # 4. ACK message
        await message.ack()
        
    except ValidationError as e:
        # Malformed → DLQ (ERR-004)
        await message.reject(requeue=False)
        
    except PipelineError as e:
        # Pipeline error → publish error (FUN-010)
        await publisher.publish_error(
            analysis_id=request.analysis_id,
            error_code=e.code,
            message=str(e)
        )
        await message.ack()
        
    except PublishError as e:
        # Publish failure → NACK for retry (ERR-005)
        logger.error("Publish failed", error=str(e))
        await message.nack(requeue=True)
```

### Verification Checklist

Before implementation, verify:
- [ ] FUN-009 implementation complete (or coordinate timing)
- [ ] `adapters/rabbitmq_adapter.py` exists and has required interface
- [ ] Consumer in `worker/consumer.py` ready to call publisher
- [ ] Message schemas in FUN-009-010-plan.md are authoritative
- [ ] Both implementations use same aio-pika version
- [ ] Exception hierarchy consistent between consumer and publisher
- [ ] Metrics namespace consistent (`queue_*` prefix)

---

**Plan Version**: 2.0  
**Last Updated**: 2026-05-01  
**Author**: AI Module Team  
**Status**: Refactored - Aligned with FUN-009 and spec.md  
**Changes from v1.0**: 
- Moved publisher from `core/` to `worker/`
- Added shared `adapters/rabbitmq_adapter.py`
- Removed pipeline modification (maintains PAT-004)
- Resolved "Open Questions" as "Design Decisions"
- Added explicit FUN-009 alignment section
