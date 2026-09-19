# benpshore-watchdog

A cooperative health/heartbeat watchdog library for embedded health monitoring in Python applications.

## What it does

This library helps applications monitor their own health by:

- **Registering named health checks** that return pass/fail verdicts
- **Registering named heartbeats** that you pulse when things are working
- **Evaluating current state on demand** to get structured status and transitions
- **Recording state-transition events** for audit trails and diagnostics

It's intentionally small and synchronous. Your application owns all decisions and remediation.

**Important:** This library is _not yet published to PyPI_. For development and testing, install from the repository.

## What it deliberately does NOT do

- **Not a daemon or service manager** — no background threads or continuous monitoring
- **Not a process supervisor** — no killing, restarting, or signaling processes
- **Not a filesystem watcher** — no inotify or polling of directories
- **Not a kernel extension** — no privileged host utilities or OS-specific integration
- **Not autonomous** — it observes signals and returns verdicts; you decide what to do

## Security model

The watchdog is a **passive observer**. It:

- Records what you tell it (health checks, heartbeats)
- Returns immutable result snapshots on demand (read-only mappings and tuples)
- Evaluates all registered checks and heartbeats synchronously on each `evaluate()` call
- Uses `time.monotonic()` for all elapsed-time calculations (immune to clock skew)
- Thread-safe for concurrent access
- Bounded history (retains only the most recent 1000 state-transition events)

**Your application owns all remediation.** If a health check fails, this library does not restart anything, kill processes, or send alerts. You decide what to do based on the returned `Evaluation`.

## Install

From the repository:

```bash
git clone <repo-url>
cd watchdog
uv sync
uv run pip install -e .
```

Or add to your `pyproject.toml`:

```toml
dependencies = [
    "benpshore-watchdog @ file:///<path-to-watchdog>",
]
```

## Quick start

```python
from benpshore_watchdog import Watchdog, Status

# Create a watchdog
watchdog = Watchdog()

# Register a periodic health check
watchdog.register_check(
    "database",
    check=lambda: check_db_connection(),  # returns True if healthy
    interval_seconds=30,
)

# Register a heartbeat (call it when your worker is alive)
watchdog.register_heartbeat(
    "background_task",
    timeout_seconds=60,
)

# Somewhere in your worker loop
def worker():
    while True:
        # ... do work ...
        watchdog.heartbeat("background_task")

# Evaluate health on demand
evaluation = watchdog.evaluate()

# Check results
if not evaluation.is_healthy():
    print("System is unhealthy:")
    for name, item_status in evaluation.items.items():
        if item_status.status != Status.HEALTHY:
            print(f"  {name}: {item_status.status.value}")
            if item_status.last_error:
                print(f"    Error: {item_status.last_error}")

# Check for recent state changes
for transition in evaluation.transitions:
    print(f"State change: {transition.name} "
          f"{transition.from_status.value} → {transition.to_status.value}")
```

## Health checks

A health check is a callable that returns strictly `True` (healthy) or `False` (failed). The callback must return a boolean; truthy/falsy values are rejected. If it raises an exception, it's caught and recorded as a failed status with diagnostic text.

The `interval_seconds` parameter is validated but not enforced by the watchdog. It's metadata for your application to use when deciding how often to call `evaluate()`.

```python
watchdog.register_check(
    "cache",
    check=lambda: len(cache) > 0,
    interval_seconds=30,  # Metadata: your app can use this to throttle evaluate()
)

# Evaluate — this runs the check synchronously
result = watchdog.evaluate()
print(result.items["cache"].status)  # Status.HEALTHY or Status.FAILED
```

**Callback exceptions are contained:**

```python
def risky_check():
    raise ConnectionError("cannot reach service")

watchdog.register_check("service", check=risky_check, interval_seconds=30)
result = watchdog.evaluate()

# Status is FAILED, error text is captured
print(result.items["service"].status)      # Status.FAILED
print(result.items["service"].last_error)  # "ConnectionError: cannot reach service"
```

**Non-bool return values are rejected:**

```python
def bad_check():
    return "yes"  # Not a bool!

watchdog.register_check("bad", check=bad_check, interval_seconds=30)
result = watchdog.evaluate()

print(result.items["bad"].status)      # Status.FAILED
print(result.items["bad"].last_error)  # "Check must return bool, got str"
```

## Heartbeats

A heartbeat is a signal you emit when a worker is alive. If you don't emit it within the timeout, the watchdog marks it stale.

```python
watchdog.register_heartbeat(
    "worker",
    timeout_seconds=60,  # Stale if no beat for 60s
)

# Somewhere in your worker
watchdog.heartbeat("worker")

# Evaluate
result = watchdog.evaluate()
print(result.items["worker"].status)  # Status.HEALTHY or Status.STALE or Status.UNKNOWN
```

**States:**

- `UNKNOWN`: No heartbeat recorded yet
- `HEALTHY`: Heartbeat recorded within timeout
- `STALE`: Timeout elapsed since last heartbeat
- `FAILED`: Health check returned False or raised

## Testing with injected clocks

For deterministic testing without sleep, inject a clock:

```python
import pytest
from benpshore_watchdog import Watchdog, Status

def test_heartbeat_stale():
    clock_time = [0.0]
    
    def fake_clock():
        return clock_time[0]
    
    watchdog = Watchdog(monotonic_clock=fake_clock)
    watchdog.register_heartbeat("worker", timeout_seconds=60)
    
    # Heartbeat at t=10
    clock_time[0] = 10.0
    watchdog.heartbeat("worker")
    result1 = watchdog.evaluate()
    assert result1.items["worker"].status == Status.HEALTHY
    
    # At t=80, it's stale
    clock_time[0] = 80.0
    result2 = watchdog.evaluate()
    assert result2.items["worker"].status == Status.STALE
```

No `time.sleep()` needed. The watchdog uses `time.monotonic()` everywhere by default.

## State transitions

Every `evaluate()` call returns a list of state transitions that occurred since the last evaluation:

```python
result = watchdog.evaluate()

for transition in result.transitions:
    print(f"{transition.name}: "
          f"{transition.from_status.value} → {transition.to_status.value} "
          f"at {transition.timestamp}")
```

Transitions are bounded; the watchdog retains only the most recent 1000 transition events.

## Names

Item names must be non-empty strings of 256 characters or fewer, containing only alphanumeric characters, dots, dashes, and underscores:

- Valid: `worker`, `cache-1`, `task_1`, `db.primary`
- Invalid: `worker@host`, ``, ` ` (space)

Duplicate names across checks and heartbeats are rejected.

## Thread safety

All operations are protected by a lock. Concurrent heartbeat recording, checks, and evaluation are safe:

```python
import threading

watchdog = Watchdog()
watchdog.register_heartbeat("worker", timeout_seconds=60)

def beat():
    for _ in range(1000):
        watchdog.heartbeat("worker")

# Multiple threads can safely record heartbeats
threads = [threading.Thread(target=beat) for _ in range(10)]
for t in threads:
    t.start()
for t in threads:
    t.join()

result = watchdog.evaluate()
assert result.items["worker"].status == Status.HEALTHY
```

## API reference

### `Watchdog(monotonic_clock=None)`

Create a watchdog. Optionally inject a clock for testing.

### `register_check(name, check, interval_seconds)`

Register a health check.

- `name` (str): Unique name
- `check` (Callable[[], bool]): Must return strictly `True` or `False` (non-bool values cause FAILED status)
- `interval_seconds` (float): Metadata for your application (must be positive, real number; not nan/inf/bool)

Raises `InvalidNameError`, `InvalidIntervalError`, or `ValueError` if duplicate or if interval_seconds is not a finite positive real number.

### `register_heartbeat(name, timeout_seconds)`

Register a heartbeat.

- `name` (str): Unique name
- `timeout_seconds` (float): Timeout before marking stale (must be positive, real number; not nan/inf/bool)

Raises `InvalidNameError`, `InvalidIntervalError`, or `ValueError` if duplicate or if timeout_seconds is not a finite positive real number.

### `heartbeat(name)`

Record a heartbeat for a registered item. Raises `KeyError` if not registered as a heartbeat.

### `evaluate() -> Evaluation`

Evaluate current state synchronously (runs all registered checks). Returns an immutable snapshot:

- `timestamp` (float): Evaluation time (from clock)
- `items` (MappingProxyType[str, ItemStatus]): Read-only mapping of item statuses
- `transitions` (Tuple[Transition, ...]): Immutable tuple of state changes since last evaluation
- `is_healthy()`: True if all items are healthy

### `get_history() -> List[Transition]`

Get bounded history of state transitions (up to 1000).

## Example: Monitoring a background worker

```python
from benpshore_watchdog import Watchdog
import time
import threading

watchdog = Watchdog()

# Register a heartbeat for the worker
watchdog.register_heartbeat("worker", timeout_seconds=5)

def background_worker():
    """A background task that signals it's alive."""
    for i in range(10):
        print(f"Working... {i}")
        # ... do real work ...
        watchdog.heartbeat("worker")
        time.sleep(1)

def monitor_health():
    """Check health periodically."""
    for i in range(20):
        result = watchdog.evaluate()
        if result.is_healthy():
            print("✓ System healthy")
        else:
            print("✗ System unhealthy")
            for name, status in result.items.items():
                if status.status.value != "healthy":
                    print(f"  {name}: {status.status.value}")
        time.sleep(1)

if __name__ == "__main__":
    # Run both concurrently in separate threads
    worker_thread = threading.Thread(target=background_worker)
    monitor_thread = threading.Thread(target=monitor_health)
    
    worker_thread.start()
    monitor_thread.start()
    
    worker_thread.join()
    monitor_thread.join()
```

## Contributing

```bash
# Clone and set up
uv sync

# Run tests
uv run pytest

# Run tests with coverage
uv run pytest tests/
```

See `CONTRIBUTING.md` for more.

## License

MIT
