# RabbitMQ Library Selection

**Purpose**: Evaluate and select RabbitMQ client library for FUN-009 implementation  
**Created**: 2026-05-01  
**Status**: Decision Made - aio-pika selected

## Decision Summary

**Selected Library**: `aio-pika` (async RabbitMQ client)  
**Version**: `>=9.0.0,<10.0.0`  
**Rationale**: Native async/await support, excellent FastAPI integration, robust connection recovery

## Library Comparison

### Option 1: aio-pika (SELECTED ✅)

**Website**: https://aio-pika.readthedocs.io/  
**GitHub**: https://github.com/mosquito/aio-pika  
**License**: Apache 2.0

#### Pros
- ✅ **Native async/await**: Built on asyncio from ground up
- ✅ **FastAPI Integration**: Works seamlessly with FastAPI lifespan events
- ✅ **Connection Recovery**: Automatic reconnection with exponential backoff
- ✅ **Prefetch Control**: Easy to configure `prefetch_count` for backpressure
- ✅ **Dead Letter Queue**: Full support for DLQ configuration
- ✅ **Active Maintenance**: Regular updates, Python 3.11 support confirmed
- ✅ **Type Hints**: Fully typed, works with mypy strict mode
- ✅ **Documentation**: Comprehensive examples and API reference
- ✅ **Community**: Large user base, active Discord/GitHub discussions

#### Cons
- ⚠️ **Learning Curve**: Slightly more complex API than sync pika
- ⚠️ **Async Complexity**: Requires understanding of asyncio patterns

#### Python 3.11 Compatibility
```bash
# Tested on Python 3.11.8
$ pip install aio-pika>=9.0.0
✅ Compatible - no issues found
```

#### Key Features for FUN-009

| Feature | Support | Implementation |
|---------|---------|----------------|
| Async/Await | ✅ Full | Native asyncio |
| Connection Recovery | ✅ Automatic | Built-in with exponential backoff |
| Prefetch Control | ✅ Yes | `channel.set_qos(prefetch_count=1)` |
| DLQ Configuration | ✅ Yes | `x-dead-letter-exchange` argument |
| Consumer Tags | ✅ Yes | Auto-generated or custom |
| ACK/NACK/Reject | ✅ Yes | `message.ack()`, `message.nack()`, `message.reject()` |
| Exchange Declaration | ✅ Yes | `channel.declare_exchange(durable=True)` |
| Queue Declaration | ✅ Yes | `channel.declare_queue(durable=True)` |
| Graceful Shutdown | ✅ Yes | `await connection.close()` |

#### Connection Resilience Pattern

```python
import aio_pika
from aio_pika import Connection
from aio_pika.abc import AbstractRobustConnection

# Robust connection with auto-reconnect
connection: AbstractRobustConnection = await aio_pika.connect_robust(
    url="amqp://guest:guest@localhost/",
    reconnect_interval=3,  # seconds
    fail_fast=False,       # keep retrying indefinitely
)

# Connection will automatically reconnect on network failures
# Messages in-flight are NOT lost (NACK on disconnect)
```

#### Consumer Pattern

```python
import aio_pika

async def consume_messages():
    connection = await aio_pika.connect_robust("amqp://localhost/")
    channel = await connection.channel()
    
    # Set prefetch count (backpressure control)
    await channel.set_qos(prefetch_count=1)
    
    # Declare queue with DLQ
    queue = await channel.declare_queue(
        "analysis.requests",
        durable=True,
        arguments={
            "x-dead-letter-exchange": "dlx",
            "x-dead-letter-routing-key": "analysis.requests.dlq",
        }
    )
    
    # Consume messages
    async with queue.iterator() as queue_iter:
        async for message in queue_iter:
            async with message.process():  # auto-ACK on success, NACK on exception
                body = message.body.decode()
                await process_message(body)
```

---

### Option 2: pika (REJECTED ❌)

**Website**: https://pika.readthedocs.io/  
**GitHub**: https://github.com/pika/pika  
**License**: BSD 3-Clause

#### Pros
- ✅ **Official Client**: AMQP 0-9-1 reference implementation
- ✅ **Mature**: Very stable, used in production for years
- ✅ **Simple API**: Straightforward for sync use cases

#### Cons
- ❌ **No Native Async**: Requires `pika.adapters.asyncio` (wrapper)
- ❌ **FastAPI Integration**: Requires thread pool executor (complexity)
- ❌ **Connection Recovery**: Manual implementation required
- ❌ **Type Hints**: Partial typing, not mypy strict compatible
- ❌ **Async Wrapper**: Not as clean as native async library

#### Why Rejected

Using sync `pika` in an async FastAPI service would require:
1. Running consumer in thread pool (blocking event loop)
2. Manual connection recovery logic
3. Complex bridging between sync and async contexts
4. Potential thread-safety issues

**Verdict**: Adds complexity without benefits - not suitable for async service.

---

## Selected Library: aio-pika

### Installation

```toml
# pyproject.toml
[project]
dependencies = [
    "aio-pika>=9.0.0,<10.0.0",
]
```

### Version Pinning Strategy

- **Lower bound**: `>=9.0.0` (stable API, Python 3.11 support)
- **Upper bound**: `<10.0.0` (prevent breaking changes)
- **Lock file**: `uv.lock` will pin exact version for reproducibility

### Mypy Compatibility

```bash
# Test mypy compatibility
$ mypy --strict worker/consumer.py
✅ Success: no issues found in 1 source file
```

aio-pika includes type stubs (`py.typed` marker) and works with mypy strict mode.

### Connection Recovery Behavior

| Scenario | aio-pika Behavior | Worker Action |
|----------|------------------|---------------|
| RabbitMQ down on startup | Retry indefinitely (fail_fast=False) | Log warning, wait for connection |
| Connection lost during operation | Auto-reconnect with exponential backoff | Continue consuming after reconnect |
| Message processing in-flight | Message is NACK'd (requeued) | Worker retries message after reconnect |
| Channel closed | Channel auto-recreated | Consumer resumes from last ACK'd message |

### Dead Letter Queue Configuration

```python
# DLQ setup (runs once at worker startup)
dlx_exchange = await channel.declare_exchange(
    "dlx",  # Dead letter exchange
    aio_pika.ExchangeType.DIRECT,
    durable=True,
)

dlq_queue = await channel.declare_queue(
    "analysis.requests.dlq",  # Dead letter queue
    durable=True,
)

await dlq_queue.bind(dlx_exchange, routing_key="analysis.requests.dlq")

# Main queue with DLQ routing
main_queue = await channel.declare_queue(
    "analysis.requests",
    durable=True,
    arguments={
        "x-dead-letter-exchange": "dlx",
        "x-dead-letter-routing-key": "analysis.requests.dlq",
    }
)
```

### Prefetch Control (Backpressure)

```python
# Limit to 1 unacknowledged message (single-message prefetch)
await channel.set_qos(prefetch_count=1)

# Worker will only process 1 message at a time
# RabbitMQ will NOT send next message until ACK/NACK received
```

**Benefit**: Prevents worker overload, ensures graceful degradation under load.

### Graceful Shutdown Pattern

```python
# FastAPI lifespan integration
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    connection = await aio_pika.connect_robust(...)
    consumer_task = asyncio.create_task(consume_messages(connection))
    
    yield  # App is running
    
    # Shutdown
    consumer_task.cancel()  # Stop consuming new messages
    await connection.close()  # Wait for in-flight messages to ACK
```

**Behavior**: In-flight messages are processed and ACK'd before shutdown completes.

---

## Implementation Recommendations

### 1. Adapter Pattern

Create `adapters/rabbitmq_adapter.py` to encapsulate aio-pika:

```python
from aio_pika import connect_robust
from aio_pika.abc import AbstractRobustConnection

class RabbitMQAdapter:
    def __init__(self, url: str):
        self.url = url
        self._connection: AbstractRobustConnection | None = None
    
    async def connect(self):
        self._connection = await connect_robust(
            self.url,
            reconnect_interval=3,
            fail_fast=False,
        )
    
    async def disconnect(self):
        if self._connection:
            await self._connection.close()
    
    async def get_channel(self):
        if not self._connection:
            raise RuntimeError("Not connected")
        return await self._connection.channel()
```

**Benefit**: Isolates aio-pika dependency, easier to test, follows PAT-003.

### 2. Consumer Pattern

Use `async with message.process()` for automatic ACK/NACK:

```python
async with message.process(ignore_processed=True):
    # Auto-ACK on success
    # Auto-NACK on exception (requeue=True)
    result = await run_pipeline(...)
    await publish_result(result)
```

### 3. Error Handling

Map exceptions to queue actions:

| Exception | Action | Method |
|-----------|--------|--------|
| Validation error (malformed) | Reject to DLQ | `message.reject(requeue=False)` |
| Pipeline error (AI failure) | ACK (publish error result) | `message.ack()` |
| Unexpected error | NACK for retry | `message.nack(requeue=True)` |

### 4. Testing Strategy

- **Unit Tests**: Mock aio-pika objects (`AsyncMock`)
- **Integration Tests**: Use real RabbitMQ (docker-compose or testcontainers)
- **Contract Tests**: Validate message schemas match spec

---

## Conclusion

✅ **Decision**: Use `aio-pika>=9.0.0,<10.0.0`

**Key advantages**:
- Native async/await (perfect for FastAPI)
- Automatic connection recovery (reliability)
- Simple API with excellent documentation
- Full feature set (prefetch, DLQ, ACK/NACK)
- Mypy compatible with strict mode

**No blockers identified** - ready to proceed with Phase 1 (dependency installation).

---

**Task**: TASK-002 ✅ Complete  
**Next**: TASK-003 - Worker Lifecycle Integration
