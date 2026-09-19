# Contributing

## Setup

Install dependencies and development tools:

```bash
uv sync
```

## Testing

Run the test suite:

```bash
uv run pytest
```

Run tests with verbose output:

```bash
uv run pytest -v
```

Run a specific test:

```bash
uv run pytest tests/test_watchdog.py::TestHeartbeatBasics::test_register_heartbeat
```

## Code style

This project uses `ruff` for linting:

```bash
uv run ruff check src/ tests/
uv run ruff format src/ tests/
```

## Before submitting

1. Write tests for new features
2. Ensure all tests pass: `uv run pytest`
3. Lint your changes: `uv run ruff check src/ tests/`
4. Format code: `uv run ruff format src/ tests/`
5. Verify imports work from the public API

## Design principles

- **Small and focused**: A cooperative watchdog, not a framework
- **Safe by default**: No background threads, no autonomous decisions, no command execution
- **Synchronous**: No async complexity
- **Testable**: Injected clock, no real elapsed time
- **Thread-safe**: Protected by locks, but no background threads
- **Zero runtime dependencies**: Only stdlib

## Keeping it small

- No auxiliary tools or build systems beyond `uv`
- No typing machinery, formatting runners, or release automation
- Tests cover the public API and core scenarios
- One module for the library core; tests alongside

If you're adding a feature, ask: does the embedding application own all decisions about what to do with the result? If not, it doesn't belong here.
