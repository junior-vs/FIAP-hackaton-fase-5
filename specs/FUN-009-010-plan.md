# Implementation Plan: FUN-009 & FUN-010 - Asynchronous RabbitMQ Workflow

**Requirements**:
- **FUN-009**: The system MUST consume asynchronous jobs from `analysis.requests`
- **FUN-010**: The system MUST publish asynchronous results to `analysis.results`

**Status**: Planning Complete
**Created**: 2026-05-01
**Estimated Effort**: 2-3 weeks

---

## 1. Problem Statement

Currently, the AI Module only supports synchronous diagram analysis via `POST /analyze`. We need to add asynchronous processing capabilities through RabbitMQ to:

1. **Enable distributed processing** - Multiple orchestrator instances can submit jobs
2. **Decouple submission from processing** - Clients don't wait for slow AI analysis
3. **Support scalability** - Multiple worker instances can process jobs in parallel
4. **Provide reliability** - Messages persist if service restarts

### Requirements Summary

**FUN-009 (Consumer)**:
- Consume messages from `analysis.requests` queue
- Decode base64-encoded file bytes
- Validate message schema (reject malformed → DLQ)
- Reuse existing analysis pipeline (PAT-004)
- Apply security boundary validation (SEC-002)

**FUN-010 (Publisher)**:
- Publish success/error results to `analysis.results` queue
- Support both success reports and error messages
- Ensure durable/persistent message delivery
- Surface publishing failures explicitly (ERR-005)
- Include full report schema (DAT-003)

**Related Requirements**:
- PAT-004: Reuse shared pipeline behavior
- ERR-004: Reject malformed messages without pipeline execution
- ERR-005: Surface publish failures for retry
- OBS-004: Observable queue operations (logs + metrics)

---

## 2. Proposed Approach

### Architecture Strategy

```
┌─────────────────────────────────────────────────────────────────┐
│                          RabbitMQ Broker                        │
│                                                                 │
│  analysis.requests ──────────────────▶ analysis.results        │
│  (input queue)                         (output queue)           │
└─────────────────────────────────────────────────────────────────┘
         │                                         ▲
         │ consume                        publish  │
         │                                         │
         ▼                                         │
┌─────────────────────────────────────────────────────────────────┐
│                        AI Module Service                        │
│                                                                 │
│  ┌─────────────────┐     ┌──────────────────┐                  │
│  │  HTTP Handler   │     │  Queue Worker    │                  │
│  │  POST /analyze  │     │  (New Component) │                  │
│  └────────┬────────┘     └────────┬─────────┘                  │
│           │                       │                             │
│           │    ┌──────────────────┘                             │
│           │    │                                                │
│           ▼    ▼                                                │
│  ┌──────────────────────────────────────┐                      │
│  │  Core Analysis Pipeline (Shared)     │                      │
│  │  - File validation                   │                      │
│  │  - Image processing                  │                      │
│  │  - LLM analysis                      │                      │
│  │  - Report validation                 │                      │
│  └──────────────────────────────────────┘                      │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Key Decisions

1. **Library**: Use `aio-pika` (async RabbitMQ client for Python)
   - Native async/await support (matches FastAPI)
   - Robust connection management
   - Compatible with Python 3.11

2. **Architecture**: New `worker/` module at same level as `api/`
   - `worker/consumer.py` - Message consumption logic
   - `worker/publisher.py` - Result publishing logic
   - `worker/__main__.py` - Worker entry point
   - Keeps queue concerns separate from HTTP API

3. **Integration Point**: Extend existing pipeline, don't replace it
   - Pipeline accepts file bytes/metadata (already does)
   - Add optional `publisher` parameter to pipeline
   - HTTP flow: publisher=None (return to caller)
   - Queue flow: publisher=ResultPublisher (publish to queue)

4. **Lifecycle**: Use FastAPI lifespan events
   - Connect to RabbitMQ on startup
   - Start consumer as background task
   - Graceful shutdown on termination

5. **Error Handling**:
   - Malformed messages → Reject (nack) → DLQ
   - Pipeline errors → Publish error result
   - Publish failures → Log + raise (message auto-retries per RabbitMQ policy)

---

## 3. Implementation Phases

### Phase 1: Foundation & Dependencies (2-3 days)

**Goal**: Set up RabbitMQ infrastructure and connection management

**Tasks**:
- Add `aio-pika>=9.0.0` to dependencies
- Add RabbitMQ configuration to settings (host, port, vhost, credentials)
- Create `adapters/rabbitmq_adapter.py` for connection pooling
- Add connection health check to `/health` endpoint
- Test connection management (connect, disconnect, reconnect)

**Deliverables**:
- ✅ RabbitMQ connection working
- ✅ Settings support queue configuration
- ✅ Health endpoint shows queue status

### Phase 2: Message Schemas & Validation (1-2 days)

**Goal**: Define and validate queue message contracts

**Tasks**:
- Create `models/queue.py` with Pydantic models:
  - `QueueRequest` (analysis_id, file_bytes_b64, file_name, context_text)
  - `QueueSuccessResult` (analysis_id, status, report, metadata)
  - `QueueErrorResult` (analysis_id, status, error_code, message)
- Add validation rules matching spec (field requirements, length limits)
- Write unit tests for schema validation (valid/invalid cases)

**Deliverables**:
- ✅ Queue message schemas defined
- ✅ Validation prevents malformed messages
- ✅ Schemas match specification exactly

### Phase 3: Consumer Implementation (3-4 days)

**Goal**: Consume messages from `analysis.requests` and process them

**Tasks**:
- Create `worker/consumer.py`:
  - Declare queue and bindings
  - Consume messages with single prefetch
  - Validate schema (reject malformed → nack)
  - Decode base64 file bytes
  - Call analysis pipeline
  - Handle pipeline exceptions
- Integrate consumer with FastAPI lifespan
- Add structured logging for queue events
- Add metrics (messages_consumed, messages_rejected, processing_time)

**Deliverables**:
- ✅ Consumer processes valid messages
- ✅ Malformed messages rejected to DLQ
- ✅ Reuses existing pipeline (no duplication)
- ✅ Observable through logs/metrics

### Phase 4: Publisher Implementation (2-3 days)

**Goal**: Publish results to `analysis.results`

**Tasks**:
- Create `worker/publisher.py`:
  - Format success results (status="success", report, metadata)
  - Format error results (status="error", error_code, message)
  - Publish with persistence/durability
  - Handle publish failures (log + raise for retry)
- Integrate publisher into pipeline flow
- Add metrics (messages_published, publish_failures)
- Add structured logging for publish events

**Deliverables**:
- ✅ Success results published correctly
- ✅ Error results published correctly
- ✅ Publishing failures surfaced explicitly
- ✅ Messages are durable/persistent

### Phase 5: Testing (3-4 days)

**Goal**: Comprehensive test coverage for queue functionality

**Tasks**:
- **Unit Tests**:
  - Queue message schema validation
  - Consumer message handling (valid, invalid, decode errors)
  - Publisher formatting (success, error)
  - Connection adapter (connect, disconnect, retry)

- **Integration Tests** (with test RabbitMQ instance):
  - End-to-end: publish request → consume → analyze → publish result
  - Malformed message → DLQ
  - Pipeline error → error result published
  - Connection loss → reconnect

- **Contract Tests**:
  - Request message schema matches spec
  - Success result schema matches spec
  - Error result schema matches spec

**Deliverables**:
- ✅ ≥80% test coverage maintained
- ✅ All queue scenarios tested
- ✅ Integration tests with real RabbitMQ

### Phase 6: Documentation & Operations (2 days)

**Goal**: Operational readiness and documentation

**Tasks**:
- Update README with:
  - RabbitMQ setup instructions
  - Queue configuration guide
  - Worker deployment instructions
- Create operations runbook:
  - Starting/stopping worker
  - Monitoring queue health
  - Handling DLQ messages
  - Troubleshooting connection issues
- Document queue message contracts
- Add architecture diagrams

**Deliverables**:
- ✅ Complete setup documentation
- ✅ Operations runbook for team
- ✅ Architecture diagrams updated

---

## 4. Dependencies & Risks

### External Dependencies

| Dependency | Impact | Mitigation |
|------------|--------|------------|
| RabbitMQ broker availability | Critical - worker can't function | Health checks, graceful degradation, retry logic |
| `aio-pika` library | Core async client | Well-maintained, 9.x stable, fallback to `pika` if needed |
| Message format compatibility | Must match orchestrator | Contract tests, schema validation |

### Technical Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| Message queue fills up | Medium | High | Monitor queue depth metrics, implement backpressure |
| Connection drops during processing | Medium | Medium | Auto-reconnect with exponential backoff, message redelivery |
| Base64 decoding memory usage | Low | Medium | Validate size limits before decode, stream if possible |
| DLQ grows unbounded | Low | Medium | Monitor DLQ depth, alert on threshold |
| Publishing failures cause message loss | Medium | High | Explicit error surfacing (ERR-005), rely on RabbitMQ redelivery |

### Implementation Risks

| Risk | Mitigation |
|------|------------|
| Breaking existing HTTP flow | Comprehensive testing of HTTP endpoint before/after |
| Pipeline modifications affect both flows | No pipeline changes - only optional publisher parameter |
| Performance degradation | Load testing with queue workload, metrics monitoring |
| Deployment complexity | Document deployment steps, use Docker Compose for local dev |

---

## 5. Testing Strategy

### Test Pyramid

```
                    ┌─────────────────┐
                    │  Contract Tests │  (6 tests)
                    │  Schema validity│
                    └─────────────────┘
                 ┌──────────────────────┐
                 │  Integration Tests   │  (12 tests)
                 │  End-to-end with     │
                 │  real RabbitMQ       │
                 └──────────────────────┘
            ┌────────────────────────────────┐
            │      Unit Tests                │  (25 tests)
            │  Consumer, Publisher, Models   │
            │  Connection, Validation        │
            └────────────────────────────────┘
```

### Test Environments

- **Unit**: Mocked RabbitMQ connections, isolated component tests
- **Integration**: Docker Compose with RabbitMQ container
- **Contract**: JSONSchema validation against specification

### Coverage Targets

- Overall: ≥80% line coverage
- Critical paths (consume, publish): 100% coverage
- Error handling: All error paths tested

---

## 6. Success Criteria

### Functional Requirements

- ✅ Consumer receives and processes messages from `analysis.requests`
- ✅ Base64 file decoding works correctly
- ✅ Malformed messages rejected without pipeline execution (ERR-004)
- ✅ Pipeline behavior reused by both HTTP and queue flows (PAT-004)
- ✅ Publisher sends success results to `analysis.results`
- ✅ Publisher sends error results to `analysis.results`
- ✅ Publishing failures surfaced explicitly (ERR-005)
- ✅ Messages are durable/persistent
- ✅ Report schema includes all required fields (DAT-003)

### Non-Functional Requirements

- ✅ Connection resilience (auto-reconnect on failure)
- ✅ Graceful startup/shutdown (FastAPI lifespan)
- ✅ Structured logging for all queue events (OBS-004)
- ✅ Prometheus metrics for queue operations (OBS-004)
- ✅ Health endpoint shows queue status
- ✅ Test coverage ≥80%
- ✅ Complete operational documentation

### Acceptance Tests

1. **Happy Path**: Submit valid message → receive success result
2. **Invalid Schema**: Submit malformed message → rejected to DLQ
3. **Pipeline Error**: Submit valid message causing AI failure → error result published
4. **Connection Loss**: Disconnect RabbitMQ mid-processing → auto-reconnect
5. **Publish Failure**: Simulate publish error → failure logged and surfaced
6. **Load Test**: Process 100 messages → all complete successfully

---

## 7. Deployment Considerations

### Configuration

New environment variables required:

```bash
# RabbitMQ Connection
RABBITMQ_HOST=localhost
RABBITMQ_PORT=5672
RABBITMQ_VHOST=/
RABBITMQ_USER=guest
RABBITMQ_PASSWORD=guest

# Queue Configuration
RABBITMQ_REQUEST_QUEUE=analysis.requests
RABBITMQ_RESULT_QUEUE=analysis.results
RABBITMQ_EXCHANGE=analysis
RABBITMQ_ROUTING_KEY_REQUESTS=requests
RABBITMQ_ROUTING_KEY_RESULTS=results

# Consumer Configuration
RABBITMQ_PREFETCH_COUNT=1
RABBITMQ_RECONNECT_DELAY=5
```

### Infrastructure Requirements

- **RabbitMQ Broker**: Version 3.12+ recommended
- **Queues**: Pre-created or auto-declared by consumer
- **DLQ**: Configure dead-letter exchange for malformed messages
- **Monitoring**: RabbitMQ Management UI + Prometheus metrics

### Deployment Steps

1. Deploy RabbitMQ broker (if not exists)
2. Configure queues and exchanges
3. Update AI Module configuration with RabbitMQ credentials
4. Deploy updated AI Module (includes worker)
5. Verify health endpoint shows queue status
6. Submit test message and verify result published

---

## 8. Open Questions

- [ ] **Should worker run in same process as API or separate?**
  - Current plan: Same process using FastAPI background tasks
  - Alternative: Separate worker process/container
  - Decision: Start with same process, separate if scaling needs differ

- [ ] **What's the retry policy for failed messages?**
  - Current plan: Rely on RabbitMQ redelivery (message nack'd on error)
  - Need to confirm: Max retries, backoff strategy
  - Action: Document RabbitMQ retry configuration in runbook

- [ ] **How to handle poison messages that always fail?**
  - Current plan: After N redeliveries → DLQ
  - Need to define: Redelivery limit (suggest 3)
  - Action: Configure DLQ with max redelivery count

- [ ] **Should we support message priority?**
  - Not in spec, but could be useful for urgent analyses
  - Decision: Not in scope for initial implementation

---

## 9. Next Steps

1. **Review this plan** with team for feedback/adjustments
2. **Set up development RabbitMQ** (Docker Compose)
3. **Start Phase 1** (Foundation & Dependencies)
4. **Create detailed tasks** for Phase 1 in project tracker
5. **Schedule weekly sync** to review progress and adjust plan

---

## 10. References

- **Specification**: `specs/spec.md` (FUN-009, FUN-010, PAT-004, ERR-004, ERR-005)
- **Existing Implementation**: `ai_module/src/ai_module/core/pipeline.py`
- **Library Documentation**: https://aio-pika.readthedocs.io/
- **RabbitMQ Docs**: https://www.rabbitmq.com/documentation.html

---

**Plan Status**: ✅ Ready for Implementation
**Next Action**: Team review and Phase 1 kickoff
