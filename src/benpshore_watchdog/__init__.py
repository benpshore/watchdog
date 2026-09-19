"""Cooperative health/heartbeat watchdog library for embedded health monitoring."""

from .watchdog import (
    Evaluation,
    HealthCheckCallback,
    InvalidIntervalError,
    InvalidNameError,
    Status,
    Transition,
    Watchdog,
)

__all__ = [
    "Evaluation",
    "HealthCheckCallback",
    "InvalidIntervalError",
    "InvalidNameError",
    "Status",
    "Transition",
    "Watchdog",
]

__version__ = "0.1.0"
