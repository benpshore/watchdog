"""Core watchdog implementation for cooperative health monitoring."""

import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, NamedTuple


class Status(Enum):
    """Health status of a monitored item."""

    HEALTHY = "healthy"
    STALE = "stale"
    FAILED = "failed"
    UNKNOWN = "unknown"


class Transition(NamedTuple):
    """A state transition event for a monitored item."""

    name: str
    timestamp: float
    from_status: Status
    to_status: Status
    reason: str


@dataclass
class ItemStatus:
    """Current status of a single monitored item."""

    name: str
    status: Status
    last_heartbeat: float | None = None
    last_check_time: float | None = None
    last_error: str | None = None


@dataclass
class Evaluation:
    """Result of evaluating watchdog state at a point in time."""

    timestamp: float
    items: dict[str, ItemStatus] = field(default_factory=dict)
    transitions: list[Transition] = field(default_factory=list)

    def is_healthy(self) -> bool:
        """Return True if all items are healthy."""
        if not self.items:
            return True
        return all(item.status == Status.HEALTHY for item in self.items.values())


HealthCheckCallback = Callable[[], bool]


class InvalidNameError(ValueError):
    """Raised when a name is invalid."""



class InvalidIntervalError(ValueError):
    """Raised when an interval is invalid."""



class Watchdog:
    """Cooperative health/heartbeat watchdog for embedded applications.

    This library lets applications register health checks and heartbeats,
    record heartbeats, and evaluate current state on demand. It is not a
    daemon, process supervisor, or autonomous remediation system—the
    embedding application owns all decisions and remediation.
    """

    MAX_HISTORY_EVENTS = 1000

    def __init__(self, monotonic_clock: Callable[[], float] | None = None):
        """Initialize the watchdog.

        Args:
            monotonic_clock: Optional injectable clock returning elapsed seconds.
                            Defaults to time.monotonic().
        """
        self._clock = monotonic_clock or time.monotonic
        self._lock = threading.RLock()
        self._checks: dict[str, dict[str, Any]] = {}
        self._heartbeats: dict[str, dict[str, Any]] = {}
        self._statuses: dict[str, Status] = {}
        self._transitions: deque[Transition] = deque(maxlen=self.MAX_HISTORY_EVENTS)

    def register_check(
        self,
        name: str,
        check: HealthCheckCallback,
        interval_seconds: float,
    ) -> None:
        """Register a health check.

        Args:
            name: Unique name for this check.
            check: Callable that returns True if healthy.
            interval_seconds: Expected frequency of checks.

        Raises:
            InvalidNameError: If name is empty or contains invalid characters.
            InvalidIntervalError: If interval is invalid.
            ValueError: If name is already registered.
        """
        self._validate_name(name)
        if interval_seconds <= 0:
            raise InvalidIntervalError(
                f"interval_seconds must be >0; got {interval_seconds}"
            )

        with self._lock:
            if name in self._checks or name in self._heartbeats:
                raise ValueError(f"Name '{name}' is already registered")

            self._checks[name] = {
                "check": check,
                "interval_seconds": interval_seconds,
                "last_check_time": None,
            }
            self._statuses[name] = Status.UNKNOWN

    def register_heartbeat(
        self,
        name: str,
        timeout_seconds: float,
    ) -> None:
        """Register a heartbeat.

        Args:
            name: Unique name for this heartbeat.
            timeout_seconds: Timeout before marking stale.

        Raises:
            InvalidNameError: If name is empty or contains invalid characters.
            InvalidIntervalError: If timeout is invalid.
            ValueError: If name is already registered.
        """
        self._validate_name(name)
        if timeout_seconds <= 0:
            raise InvalidIntervalError(
                f"timeout_seconds must be >0; got {timeout_seconds}"
            )

        with self._lock:
            if name in self._checks or name in self._heartbeats:
                raise ValueError(f"Name '{name}' is already registered")

            self._heartbeats[name] = {
                "timeout_seconds": timeout_seconds,
                "last_heartbeat": None,
            }
            self._statuses[name] = Status.UNKNOWN

    def heartbeat(self, name: str) -> None:
        """Record a heartbeat for a named item.

        Args:
            name: Name of the registered heartbeat.

        Raises:
            KeyError: If the name is not registered as a heartbeat.
        """
        with self._lock:
            if name not in self._heartbeats:
                raise KeyError(f"Heartbeat '{name}' is not registered")
            self._heartbeats[name]["last_heartbeat"] = self._clock()

    def evaluate(self) -> Evaluation:
        """Evaluate current watchdog state.

        Returns:
            Evaluation containing item statuses and any state transitions.
        """
        current_time = self._clock()

        with self._lock:
            statuses: dict[str, ItemStatus] = {}
            new_transitions: list[Transition] = []

            # Evaluate health checks
            for name, check_cfg in self._checks.items():
                status, error = self._eval_check(
                    name, check_cfg, current_time
                )
                self._record_transition(name, status, new_transitions, current_time)
                statuses[name] = ItemStatus(
                    name=name,
                    status=status,
                    last_check_time=check_cfg["last_check_time"],
                    last_error=error,
                )

            # Evaluate heartbeats
            for name, hb_cfg in self._heartbeats.items():
                status = self._eval_heartbeat(name, hb_cfg, current_time)
                self._record_transition(name, status, new_transitions, current_time)
                statuses[name] = ItemStatus(
                    name=name,
                    status=status,
                    last_heartbeat=hb_cfg["last_heartbeat"],
                )

            # Add transitions to bounded history
            self._transitions.extend(new_transitions)

            return Evaluation(
                timestamp=current_time,
                items=statuses,
                transitions=new_transitions,
            )

    def get_history(self) -> list[Transition]:
        """Get bounded history of state transitions.

        Returns:
            List of transitions in order.
        """
        with self._lock:
            return list(self._transitions)

    def _eval_check(
        self, name: str, check_cfg: dict[str, Any], current_time: float
    ) -> tuple[Status, str | None]:
        """Evaluate a single health check.

        Returns:
            (status, error_text or None)
        """
        try:
            result = check_cfg["check"]()
            check_cfg["last_check_time"] = current_time
            if result:
                return Status.HEALTHY, None
            else:
                return Status.FAILED, None
        except Exception as e:  # noqa: BLE001
            check_cfg["last_check_time"] = current_time
            error_text = f"{type(e).__name__}: {str(e)[:100]}"
            return Status.FAILED, error_text

    def _eval_heartbeat(
        self, name: str, hb_cfg: dict[str, Any], current_time: float
    ) -> Status:
        """Evaluate a single heartbeat.

        Returns:
            Status
        """
        last_hb = hb_cfg["last_heartbeat"]
        timeout = hb_cfg["timeout_seconds"]

        if last_hb is None:
            return Status.UNKNOWN

        elapsed = current_time - last_hb
        if elapsed <= timeout:
            return Status.HEALTHY

        return Status.STALE

    def _record_transition(
        self,
        name: str,
        new_status: Status,
        transitions: list[Transition],
        current_time: float,
    ) -> None:
        """Record a transition if status changed."""
        old_status = self._statuses[name]
        if old_status != new_status:
            self._statuses[name] = new_status
            transitions.append(
                Transition(
                    name=name,
                    timestamp=current_time,
                    from_status=old_status,
                    to_status=new_status,
                    reason=f"status changed to {new_status.value}",
                )
            )

    @staticmethod
    def _validate_name(name: str) -> None:
        """Validate a name.

        Raises:
            InvalidNameError: If name is invalid.
        """
        if not name or not isinstance(name, str):
            raise InvalidNameError("Name must be a non-empty string")
        if len(name) > 256:
            raise InvalidNameError("Name must be <= 256 characters")
        if not all(c.isalnum() or c in "-_." for c in name):
            raise InvalidNameError(
                "Name must contain only alphanumeric characters, '-', '_', or '.'"
            )
