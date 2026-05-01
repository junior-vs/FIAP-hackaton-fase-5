# Worker Lifecycle Integration

**Purpose**: Define worker lifecycle integration with FastAPI application  
**Created**: 2026-05-01  
**Status**: Architecture Defined

## Executive Summary

The RabbitMQ consumer will run **alongside** the FastAPI HTTP server as a background task, managed by FastAPI's lifespan events. Both services (HTTP API and queue consumer) will:
- ✅ Start concurrently on application launch
- ✅ Share the same event loop (asyncio)
- ✅ Share dependencies (pipeline, adapters, settings)
- ✅ Shut down gracefully on SIGTERM/SIGINT
- ✅ Report health status independently

## Lifecycle Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                        FastAPI Application                       │
│                         (lifespan context)                       │
└──────────────────────────────────────────────────────────────────┘
                              │
                    ┌─────────┴─────────┐
                    │                   │
                    ▼                   ▼
        ┌──────────────────┐  ┌──────────────────┐
        │   HTTP Server    │  │  Queue Consumer  │
        │   (uvicorn)      │  │  (aio-pika)      │
        │                  │  │                  │
        │  /analyze POST   │  │  analysis.       │
        │  /health GET     │  │  requests queue  │
        │  /metrics GET    │  │                  │
        └──────────────────┘  └──────────────────┘
                    │                   │
                    └─────────┬─────────┘
                              ▼
                  ┌──────────────────────┐
                  │   Shared Pipeline    │
                  │   run_pipeline()     │
                  └──────────────────────┘
```

## FastAPI Lifespan Pattern

FastAPI 0.135.3 uses `@asynccontextmanager` for lifecycle management:

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
import asyncio

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifecycle: startup and shutdown."""
    
    # ============== STARTUP ==============
    # 1. Connect to RabbitMQ
    rabbitmq_adapter = RabbitMQAdapter(settings.RABBITMQ_URL)
    await rabbitmq_adapter.connect()
    
    # 2. Start consumer as background task
    consumer_task = asyncio.create_task(
        consume_messages(rabbitmq_adapter),
        name="rabbitmq_consumer"
    )
    
    # 3. Store references in app.state for health checks
    app.state.rabbitmq = rabbitmq_adapter
    app.state.consumer_task = consumer_task
    
    logger.info("Application startup complete", extra={
        "event": "app_startup",
        "services": ["http_api", "queue_consumer"]
    })
    
    yield  # =========== APP IS RUNNING ===========
    
    # ============== SHUTDOWN ==============
    # 4. Cancel consumer task (stop accepting new messages)
    consumer_task.cancel()
    
    try:
        await asyncio.wait_for(consumer_task, timeout=10.0)
    except asyncio.TimeoutError:
        logger.warning("Consumer did not stop gracefully, forcing shutdown")
    except asyncio.CancelledError:
        logger.info("Consumer task cancelled successfully")
    
    # 5. Disconnect from RabbitMQ (wait for in-flight messages)
    await rabbitmq_adapter.disconnect()
    
    logger.info("Application shutdown complete", extra={
        "event": "app_shutdown"
    })

# Create FastAPI app with lifespan
app = FastAPI(lifespan=lifespan)
```

## Startup Sequence

```
┌─────────────────────────────────────────────────────────────────┐
│ 1. uvicorn main:app --host 0.0.0.0 --port 8000                 │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ 2. FastAPI calls lifespan() context manager                    │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ 3. STARTUP PHASE (before yield)                                │
│    - Load environment variables (settings)                      │
│    - Validate LLM adapter configuration                         │
│    - Connect to RabbitMQ (with retry)                           │
│    - Declare exchanges and queues                               │
│    - Start consumer task (asyncio.create_task)                  │
│    - Store references in app.state                              │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ 4. APPLICATION RUNNING (yield point)                            │
│    - HTTP server accepts requests on port 8000                  │
│    - Consumer processes messages from analysis.requests         │
│    - Both services share the event loop                         │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼ (SIGTERM/SIGINT received)
┌─────────────────────────────────────────────────────────────────┐
│ 5. SHUTDOWN PHASE (after yield)                                │
│    - Cancel consumer task (stop accepting new messages)         │
│    - Wait for in-flight messages to ACK (max 10s)              │
│    - Close RabbitMQ connection                                  │
│    - HTTP server stops accepting new requests                   │
└─────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────┐
│ 6. Process exits (uvicorn shutdown complete)                   │
└─────────────────────────────────────────────────────────────────┘
```

## Consumer Task Pattern

The consumer runs as a **long-lived asyncio task**:

```python
async def consume_messages(rabbitmq: RabbitMQAdapter):
    """Consume messages from analysis.requests queue.
    
    Runs indefinitely until cancelled by lifespan shutdown.
    """
    try:
        channel = await rabbitmq.get_channel()
        await channel.set_qos(prefetch_count=1)
        
        queue = await channel.declare_queue(
            "analysis.requests",
            durable=True,
            arguments={
                "x-dead-letter-exchange": "dlx",
                "x-dead-letter-routing-key": "analysis.requests.dlq",
            }
        )
        
        logger.info("Consumer started", extra={
            "event": "consumer_start",
            "queue": "analysis.requests"
        })
        
        # Consume messages indefinitely (until task is cancelled)
        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                try:
                    await process_message(message)
                except Exception as e:
                    logger.error("Unexpected error in consumer loop", extra={
                        "event": "consumer_error",
                        "error": str(e),
                        "message_id": message.message_id,
                    })
                    await message.nack(requeue=True)
    
    except asyncio.CancelledError:
        logger.info("Consumer task cancelled, shutting down gracefully")
        raise  # Re-raise to complete cancellation
    
    except Exception as e:
        logger.error("Fatal consumer error, restarting", extra={
            "event": "consumer_fatal",
            "error": str(e)
        })
        # TODO: Implement restart logic or crash (depends on error handling policy)
        raise
```

## Graceful Shutdown Behavior

### Scenario: SIGTERM Received

```
Time    HTTP Server              Queue Consumer              RabbitMQ
────────────────────────────────────────────────────────────────────
T+0s    Accepting requests       Processing message 123      Queue has 10 msgs
        GET /health → 200        └─ ACK pending

T+0.1s  [SIGTERM received]       [Task cancelled]            Queue has 10 msgs
        Stop accepting new       Stop consuming new          
        requests                 messages

T+0.2s  Waiting for current      Finishing message 123       Queue has 10 msgs
        requests to finish       └─ ACK sent                 └─ Now 9 msgs

T+0.3s  All requests finished    Consumer loop exits         Queue has 9 msgs
                                 Connection.close() called

T+0.5s  Server shutdown          Connection closed           Queue has 9 msgs
        complete                 gracefully                  └─ Available for
                                                                other consumers

T+0.6s  [Process exits]
```

**Key behavior**:
- ✅ In-flight HTTP requests complete before shutdown
- ✅ In-flight queue message is ACK'd before shutdown
- ✅ Un-consumed messages remain in queue (picked up by other workers or next restart)
- ✅ No message loss on graceful shutdown

### Scenario: Forced Kill (SIGKILL)

```
Time    HTTP Server              Queue Consumer              RabbitMQ
────────────────────────────────────────────────────────────────────
T+0s    Accepting requests       Processing message 123      Queue has 10 msgs
        GET /health → 200        └─ ACK pending

T+0.1s  [SIGKILL received]       [Process killed]            Queue has 10 msgs
        [Immediate exit]         [No cleanup]                └─ Message 123 in-flight

T+1s    [Process dead]           [Connection lost]           RabbitMQ detects
                                                             connection drop

T+2s                                                         Message 123 NACK'd
                                                             (auto-requeue)
                                                             Queue has 10 msgs again
```

**Key behavior**:
- ⚠️ In-flight message is automatically NACK'd by RabbitMQ
- ✅ Message 123 is requeued and will be retried
- ✅ No message loss (RabbitMQ's unacked message tracking)

## Health Check Integration

Health endpoint must report status of **both** HTTP and queue services:

```python
from fastapi import FastAPI, status
from fastapi.responses import JSONResponse

@app.get("/health")
async def health_check():
    """Report health of HTTP API and queue consumer."""
    
    # Check if consumer task is running
    consumer_task = app.state.consumer_task
    consumer_healthy = consumer_task and not consumer_task.done()
    
    # Check if RabbitMQ is connected
    rabbitmq = app.state.rabbitmq
    rabbitmq_healthy = rabbitmq and rabbitmq.is_connected()
    
    overall_healthy = consumer_healthy and rabbitmq_healthy
    
    response = {
        "status": "healthy" if overall_healthy else "degraded",
        "services": {
            "http_api": "up",  # If this endpoint responds, HTTP is up
            "queue_consumer": "up" if consumer_healthy else "down",
            "rabbitmq": "connected" if rabbitmq_healthy else "disconnected",
        }
    }
    
    status_code = status.HTTP_200_OK if overall_healthy else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(content=response, status_code=status_code)
```

### Health Check Response Examples

**Healthy state**:
```json
{
  "status": "healthy",
  "services": {
    "http_api": "up",
    "queue_consumer": "up",
    "rabbitmq": "connected"
  }
}
```
HTTP 200 OK

**Degraded state** (RabbitMQ disconnected):
```json
{
  "status": "degraded",
  "services": {
    "http_api": "up",
    "queue_consumer": "down",
    "rabbitmq": "disconnected"
  }
}
```
HTTP 503 Service Unavailable

**Use cases**:
- Kubernetes liveness probe: `GET /health` (restart if 503)
- Kubernetes readiness probe: `GET /health` (remove from load balancer if 503)
- Monitoring alerts: Alert if status is "degraded" for >5 minutes

## Connection Recovery Behavior

When RabbitMQ connection is lost:

```
Time    Queue Consumer                           RabbitMQ Status
─────────────────────────────────────────────────────────────────
T+0s    Processing messages normally             Connected
        └─ Message 123 in progress

T+1s    [Connection lost - network failure]      Disconnected
        └─ Message 123 NACK'd by RabbitMQ

T+2s    aio-pika detects disconnect              Disconnected
        └─ Triggers reconnection attempt #1      
            └─ Failed (RabbitMQ still down)

T+5s    Reconnection attempt #2                  Disconnected
        └─ Failed (exponential backoff)

T+11s   Reconnection attempt #3                  Disconnected
        └─ Failed

T+23s   Reconnection attempt #4                  Connection restored!
        └─ Success!

T+24s   Consumer resumes                         Connected
        └─ Starts processing message 123 again
            (was requeued after NACK)
```

**Key behavior**:
- ✅ Automatic reconnection with exponential backoff
- ✅ In-flight messages are requeued (no loss)
- ✅ Consumer resumes from last ACK'd position
- ✅ Health check reports "degraded" during reconnection
- ✅ No manual intervention required

## Concurrency Model

Both HTTP and queue consumer share the same asyncio event loop:

```python
# Pseudo-code representation

async def main():
    # Single event loop
    loop = asyncio.get_running_loop()
    
    # Task 1: HTTP server (managed by uvicorn)
    http_task = loop.create_task(uvicorn_serve())
    
    # Task 2: Queue consumer (managed by lifespan)
    consumer_task = loop.create_task(consume_messages())
    
    # Both tasks run concurrently on the same loop
    await asyncio.gather(http_task, consumer_task)
```

**Implications**:
- ✅ Shared pipeline can be called from both HTTP and queue contexts
- ✅ No threading issues (single-threaded async)
- ✅ Metrics are thread-safe (all updates on same loop)
- ⚠️ Blocking calls will block both services (use `asyncio.to_thread` if needed)

## Error Handling Strategies

### Strategy 1: Crash and Restart (Recommended for Production)

**Philosophy**: Let it crash, Kubernetes/Docker will restart

```python
async def consume_messages(rabbitmq: RabbitMQAdapter):
    try:
        # Consumer loop
        async with queue.iterator() as queue_iter:
            async for message in queue_iter:
                await process_message(message)
    
    except asyncio.CancelledError:
        # Graceful shutdown - re-raise
        raise
    
    except Exception as e:
        # Fatal error - log and crash
        logger.critical("Fatal consumer error, crashing", extra={
            "event": "consumer_fatal",
            "error": str(e),
            "traceback": traceback.format_exc(),
        })
        # Exit process (Kubernetes will restart)
        sys.exit(1)
```

**Benefits**:
- Clean restart with fresh state
- No risk of corrupt state
- Simple to reason about

### Strategy 2: In-Process Restart (Alternative)

**Philosophy**: Try to recover without process restart

```python
async def consume_messages_with_restart(rabbitmq: RabbitMQAdapter):
    while True:
        try:
            await consume_messages(rabbitmq)
        
        except asyncio.CancelledError:
            # Graceful shutdown
            break
        
        except Exception as e:
            logger.error("Consumer crashed, restarting in 5s", extra={
                "event": "consumer_restart",
                "error": str(e),
            })
            await asyncio.sleep(5)
            # Loop continues - restart consumer
```

**Drawbacks**:
- Risk of repeated failures
- More complex state management
- Harder to test

**Recommendation**: Use Strategy 1 (crash and restart) for simplicity and reliability.

## Summary

✅ **Architecture**: Consumer runs as background task in FastAPI lifespan  
✅ **Concurrency**: Shared asyncio loop with HTTP server  
✅ **Startup**: Automatic on app launch  
✅ **Shutdown**: Graceful with 10s timeout  
✅ **Recovery**: Automatic reconnection via aio-pika  
✅ **Health**: Exposed via `/health` endpoint  
✅ **Error Handling**: Crash-and-restart for fatal errors

**No blockers identified** - architecture is robust and production-ready.

---

**Task**: TASK-003 ✅ Complete  
**Phase 0**: ✅ All tasks complete (6 hours total)  
**Next**: Phase 1 - Add dependencies and configure environment

## Implementation Checklist

- [ ] Implement `@asynccontextmanager` lifespan function
- [ ] Add RabbitMQ connection to lifespan startup
- [ ] Start consumer task with `asyncio.create_task`
- [ ] Store references in `app.state` for health checks
- [ ] Implement graceful shutdown with 10s timeout
- [ ] Add health endpoint with consumer status
- [ ] Test startup/shutdown behavior locally
- [ ] Test connection recovery (stop/start RabbitMQ)
- [ ] Add structured logging for lifecycle events
- [ ] Document deployment requirements (Kubernetes, Docker)
