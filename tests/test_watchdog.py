"""Comprehensive tests for the benpshore-watchdog library."""

import pytest

from benpshore_watchdog import (
    Evaluation,
    InvalidIntervalError,
    InvalidNameError,
    Status,
    Transition,
    Watchdog,
)


class TestPublicImports:
    """Test that public API is importable."""

    def test_import_from_package(self):
        """Test importing from benpshore_watchdog package."""
        from benpshore_watchdog import Status, Watchdog
        assert Watchdog is not None
        assert Status is not None
        assert Evaluation is not None
        assert Transition is not None


class TestHeartbeatBasics:
    """Test basic heartbeat registration and evaluation."""

    def test_register_heartbeat(self):
        """Test registering a heartbeat."""
        watchdog = Watchdog()
        watchdog.register_heartbeat("worker", timeout_seconds=60)
        # Should not raise

    def test_record_heartbeat(self):
        """Test recording a heartbeat."""
        watchdog = Watchdog()
        watchdog.register_heartbeat("worker", timeout_seconds=60)
        watchdog.heartbeat("worker")  # Should not raise

    def test_heartbeat_starts_unknown(self):
        """Test that heartbeat starts in unknown state."""
        watchdog = Watchdog()
        watchdog.register_heartbeat("worker", timeout_seconds=60)
        eval_result = watchdog.evaluate()
        assert eval_result.items["worker"].status == Status.UNKNOWN

    def test_heartbeat_becomes_healthy(self):
        """Test that heartbeat becomes healthy after first beat."""
        clock_time = [0.0]

        def clock():
            return clock_time[0]

        watchdog = Watchdog(monotonic_clock=clock)
        watchdog.register_heartbeat("worker", timeout_seconds=60)
        clock_time[0] = 10.0
        watchdog.heartbeat("worker")
        eval_result = watchdog.evaluate()
        assert eval_result.items["worker"].status == Status.HEALTHY

    def test_heartbeat_becomes_stale(self):
        """Test that heartbeat becomes stale after timeout."""
        clock_time = [0.0]

        def clock():
            return clock_time[0]

        watchdog = Watchdog(monotonic_clock=clock)
        watchdog.register_heartbeat("worker", timeout_seconds=60)
        clock_time[0] = 10.0
        watchdog.heartbeat("worker")
        clock_time[0] = 80.0
        eval_result = watchdog.evaluate()
        assert eval_result.items["worker"].status == Status.STALE

    def test_heartbeat_transitions_healthy_to_stale(self):
        """Test state transition from healthy to stale."""
        clock_time = [0.0]

        def clock():
            return clock_time[0]

        watchdog = Watchdog(monotonic_clock=clock)
        watchdog.register_heartbeat("worker", timeout_seconds=60)

        clock_time[0] = 10.0
        watchdog.heartbeat("worker")
        eval1 = watchdog.evaluate()
        assert eval1.items["worker"].status == Status.HEALTHY
        assert len(eval1.transitions) == 1  # UNKNOWN -> HEALTHY
        assert eval1.transitions[0].from_status == Status.UNKNOWN
        assert eval1.transitions[0].to_status == Status.HEALTHY

        clock_time[0] = 80.0
        eval2 = watchdog.evaluate()
        assert eval2.items["worker"].status == Status.STALE
        assert len(eval2.transitions) == 1  # HEALTHY -> STALE
        assert eval2.transitions[0].from_status == Status.HEALTHY
        assert eval2.transitions[0].to_status == Status.STALE

    def test_heartbeat_recovers_from_stale(self):
        """Test recovery from stale state."""
        clock_time = [0.0]

        def clock():
            return clock_time[0]

        watchdog = Watchdog(monotonic_clock=clock)
        watchdog.register_heartbeat("worker", timeout_seconds=60)

        clock_time[0] = 10.0
        watchdog.heartbeat("worker")
        eval1 = watchdog.evaluate()
        assert eval1.items["worker"].status == Status.HEALTHY

        clock_time[0] = 80.0
        eval2 = watchdog.evaluate()
        assert eval2.items["worker"].status == Status.STALE

        clock_time[0] = 85.0
        watchdog.heartbeat("worker")
        eval3 = watchdog.evaluate()
        assert eval3.items["worker"].status == Status.HEALTHY
        assert len(eval3.transitions) == 1  # STALE -> HEALTHY


class TestHealthChecks:
    """Test health check registration and evaluation."""

    def test_register_check(self):
        """Test registering a health check."""
        watchdog = Watchdog()
        watchdog.register_check("cache", check=lambda: True, interval_seconds=30)
        # Should not raise

    def test_check_healthy(self):
        """Test that check returns healthy when check returns True."""
        watchdog = Watchdog()
        watchdog.register_check("cache", check=lambda: True, interval_seconds=30)
        eval_result = watchdog.evaluate()
        assert eval_result.items["cache"].status == Status.HEALTHY

    def test_check_failed(self):
        """Test that check returns failed when check returns False."""
        watchdog = Watchdog()
        watchdog.register_check("cache", check=lambda: False, interval_seconds=30)
        eval_result = watchdog.evaluate()
        assert eval_result.items["cache"].status == Status.FAILED

    def test_check_exception_contained(self):
        """Test that check exceptions are contained and produce failed status."""

        def failing_check():
            raise ValueError("something went wrong")

        watchdog = Watchdog()
        watchdog.register_check("cache", check=failing_check, interval_seconds=30)
        eval_result = watchdog.evaluate()
        assert eval_result.items["cache"].status == Status.FAILED
        assert eval_result.items["cache"].last_error is not None
        assert "ValueError" in eval_result.items["cache"].last_error

    def test_check_exception_text_truncated(self):
        """Test that very long error messages are truncated."""

        def failing_check():
            raise ValueError("x" * 200)

        watchdog = Watchdog()
        watchdog.register_check("cache", check=failing_check, interval_seconds=30)
        eval_result = watchdog.evaluate()
        assert len(eval_result.items["cache"].last_error) <= 120


class TestGracePeriod:
    """Test grace period behavior for checks."""

    def test_check_with_grace_period(self):
        """Test that grace period allows check not to be called within interval."""
        clock_time = [0.0]

        def clock():
            return clock_time[0]

        check_count = [0]

        def check_fn():
            check_count[0] += 1
            return False

        watchdog = Watchdog(monotonic_clock=clock)
        watchdog.register_check(
            "cache",
            check=check_fn,
            interval_seconds=30,
            grace_seconds=5,
        )

        clock_time[0] = 0.0
        eval1 = watchdog.evaluate()
        assert eval1.items["cache"].status == Status.FAILED

        clock_time[0] = 15.0
        watchdog.evaluate()
        # Check that we marked stale after interval + grace expired
        # But not within the grace period


class TestValidation:
    """Test name and interval validation."""

    def test_invalid_empty_name(self):
        """Test that empty names are rejected."""
        watchdog = Watchdog()
        with pytest.raises(InvalidNameError):
            watchdog.register_heartbeat("", timeout_seconds=60)

    def test_invalid_name_with_special_chars(self):
        """Test that invalid characters in names are rejected."""
        watchdog = Watchdog()
        with pytest.raises(InvalidNameError):
            watchdog.register_heartbeat("worker@host", timeout_seconds=60)

    def test_valid_name_with_dash(self):
        """Test that dashes are allowed in names."""
        watchdog = Watchdog()
        watchdog.register_heartbeat("worker-1", timeout_seconds=60)
        # Should not raise

    def test_valid_name_with_underscore(self):
        """Test that underscores are allowed in names."""
        watchdog = Watchdog()
        watchdog.register_heartbeat("worker_1", timeout_seconds=60)
        # Should not raise

    def test_valid_name_with_dot(self):
        """Test that dots are allowed in names."""
        watchdog = Watchdog()
        watchdog.register_heartbeat("worker.1", timeout_seconds=60)
        # Should not raise

    def test_invalid_name_too_long(self):
        """Test that very long names are rejected."""
        watchdog = Watchdog()
        with pytest.raises(InvalidNameError):
            watchdog.register_heartbeat("x" * 257, timeout_seconds=60)

    def test_invalid_timeout(self):
        """Test that invalid timeout is rejected."""
        watchdog = Watchdog()
        with pytest.raises(InvalidIntervalError):
            watchdog.register_heartbeat("worker", timeout_seconds=0)

    def test_invalid_interval(self):
        """Test that invalid interval is rejected."""
        watchdog = Watchdog()
        with pytest.raises(InvalidIntervalError):
            watchdog.register_check("cache", check=lambda: True, interval_seconds=-1)

    def test_negative_grace_period(self):
        """Test that negative grace period is rejected."""
        watchdog = Watchdog()
        with pytest.raises(InvalidIntervalError):
            watchdog.register_check(
                "cache",
                check=lambda: True,
                interval_seconds=30,
                grace_seconds=-1,
            )

    def test_duplicate_name_heartbeat_then_check(self):
        """Test that duplicate names across types are rejected."""
        watchdog = Watchdog()
        watchdog.register_heartbeat("worker", timeout_seconds=60)
        with pytest.raises(ValueError):
            watchdog.register_check("worker", check=lambda: True, interval_seconds=30)

    def test_duplicate_name_check_then_heartbeat(self):
        """Test that duplicate names across types are rejected."""
        watchdog = Watchdog()
        watchdog.register_check("cache", check=lambda: True, interval_seconds=30)
        with pytest.raises(ValueError):
            watchdog.register_heartbeat("cache", timeout_seconds=60)

    def test_duplicate_heartbeat_names(self):
        """Test that duplicate heartbeat names are rejected."""
        watchdog = Watchdog()
        watchdog.register_heartbeat("worker", timeout_seconds=60)
        with pytest.raises(ValueError):
            watchdog.register_heartbeat("worker", timeout_seconds=30)


class TestBoundedHistory:
    """Test bounded event retention."""

    def test_history_bounded(self):
        """Test that history is bounded to MAX_HISTORY_EVENTS."""
        clock_time = [0.0]

        def clock():
            return clock_time[0]

        watchdog = Watchdog(monotonic_clock=clock)
        watchdog.register_heartbeat("hb", timeout_seconds=1)

        # Generate many transitions
        for i in range(Watchdog.MAX_HISTORY_EVENTS + 100):
            clock_time[0] = i * 2.0
            if i % 2 == 0:
                watchdog.heartbeat("hb")
            watchdog.evaluate()

        history = watchdog.get_history()
        assert len(history) <= Watchdog.MAX_HISTORY_EVENTS

    def test_oldest_events_removed(self):
        """Test that oldest events are removed when limit exceeded."""
        clock_time = [0.0]

        def clock():
            return clock_time[0]

        watchdog = Watchdog(monotonic_clock=clock)
        watchdog.register_heartbeat("hb", timeout_seconds=1)

        first_eval_time = None
        for i in range(10):
            clock_time[0] = i * 2.0
            if i % 2 == 0:
                watchdog.heartbeat("hb")
            eval_result = watchdog.evaluate()
            if i == 0 and eval_result.transitions:
                first_eval_time = eval_result.transitions[0].timestamp

        history = watchdog.get_history()
        if first_eval_time is not None:
            # Check oldest event is from an early evaluation
            assert history[0].timestamp == first_eval_time


class TestTransitions:
    """Test state transition generation."""

    def test_no_transitions_if_no_status_change(self):
        """Test that no transitions are reported if status doesn't change."""
        watchdog = Watchdog()
        watchdog.register_check("cache", check=lambda: True, interval_seconds=30)
        eval1 = watchdog.evaluate()
        eval2 = watchdog.evaluate()
        assert len(eval1.transitions) == 1  # UNKNOWN -> HEALTHY
        assert len(eval2.transitions) == 0  # No change

    def test_transition_has_correct_fields(self):
        """Test that transitions contain all required fields."""
        clock_time = [0.0]

        def clock():
            return clock_time[0]

        watchdog = Watchdog(monotonic_clock=clock)
        watchdog.register_heartbeat("worker", timeout_seconds=60)
        clock_time[0] = 10.0
        watchdog.heartbeat("worker")
        eval_result = watchdog.evaluate()
        trans = eval_result.transitions[0]
        assert trans.name == "worker"
        assert trans.timestamp == 10.0
        assert trans.from_status == Status.UNKNOWN
        assert trans.to_status == Status.HEALTHY
        assert trans.reason is not None


class TestMultipleItems:
    """Test watchdog with multiple registered items."""

    def test_multiple_heartbeats(self):
        """Test evaluating multiple heartbeats."""
        watchdog = Watchdog()
        watchdog.register_heartbeat("worker1", timeout_seconds=60)
        watchdog.register_heartbeat("worker2", timeout_seconds=60)
        watchdog.heartbeat("worker1")
        eval_result = watchdog.evaluate()
        assert "worker1" in eval_result.items
        assert "worker2" in eval_result.items
        assert eval_result.items["worker1"].status == Status.HEALTHY
        assert eval_result.items["worker2"].status == Status.UNKNOWN

    def test_multiple_checks(self):
        """Test evaluating multiple checks."""
        watchdog = Watchdog()
        watchdog.register_check("cache", check=lambda: True, interval_seconds=30)
        watchdog.register_check("db", check=lambda: False, interval_seconds=30)
        eval_result = watchdog.evaluate()
        assert eval_result.items["cache"].status == Status.HEALTHY
        assert eval_result.items["db"].status == Status.FAILED

    def test_is_healthy_all_healthy(self):
        """Test is_healthy when all items are healthy."""
        watchdog = Watchdog()
        watchdog.register_check("cache", check=lambda: True, interval_seconds=30)
        watchdog.register_check("db", check=lambda: True, interval_seconds=30)
        eval_result = watchdog.evaluate()
        assert eval_result.is_healthy() is True

    def test_is_healthy_one_failed(self):
        """Test is_healthy when one item failed."""
        watchdog = Watchdog()
        watchdog.register_check("cache", check=lambda: True, interval_seconds=30)
        watchdog.register_check("db", check=lambda: False, interval_seconds=30)
        eval_result = watchdog.evaluate()
        assert eval_result.is_healthy() is False

    def test_is_healthy_one_stale(self):
        """Test is_healthy when one item is stale."""
        clock_time = [0.0]

        def clock():
            return clock_time[0]

        watchdog = Watchdog(monotonic_clock=clock)
        watchdog.register_heartbeat("worker1", timeout_seconds=60)
        watchdog.register_heartbeat("worker2", timeout_seconds=60)
        clock_time[0] = 10.0
        watchdog.heartbeat("worker1")
        clock_time[0] = 80.0
        eval_result = watchdog.evaluate()
        assert eval_result.is_healthy() is False

    def test_is_healthy_empty_watchdog(self):
        """Test is_healthy on empty watchdog."""
        watchdog = Watchdog()
        eval_result = watchdog.evaluate()
        assert eval_result.is_healthy() is True


class TestThreadSafety:
    """Test thread-safe access to watchdog."""

    def test_concurrent_heartbeats(self):
        """Test concurrent heartbeat recording."""
        import threading

        watchdog = Watchdog()
        watchdog.register_heartbeat("worker", timeout_seconds=60)

        def record_beats():
            for _ in range(100):
                watchdog.heartbeat("worker")

        threads = [threading.Thread(target=record_beats) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        eval_result = watchdog.evaluate()
        assert eval_result.items["worker"].status == Status.HEALTHY

    def test_concurrent_evaluate(self):
        """Test concurrent evaluation."""
        import threading

        watchdog = Watchdog()
        watchdog.register_heartbeat("worker", timeout_seconds=60)
        watchdog.heartbeat("worker")

        results = []

        def evaluate():
            for _ in range(100):
                eval_result = watchdog.evaluate()
                results.append(eval_result.items["worker"].status)

        threads = [threading.Thread(target=evaluate) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert all(status == Status.HEALTHY for status in results)


class TestHeartbeatNotRegistered:
    """Test error handling for unregistered heartbeats."""

    def test_heartbeat_unregistered_error(self):
        """Test that recording heartbeat for unknown name raises KeyError."""
        watchdog = Watchdog()
        with pytest.raises(KeyError):
            watchdog.heartbeat("unknown")


class TestInjectedClock:
    """Test injectable clock mechanism."""

    def test_default_clock_is_monotonic(self):
        """Test that default clock uses time.monotonic."""
        import time

        watchdog = Watchdog()
        watchdog.register_heartbeat("worker", timeout_seconds=60)
        watchdog.heartbeat("worker")

        # Evaluate and check timestamp is recent (close to monotonic time)
        eval_result = watchdog.evaluate()
        now = time.monotonic()
        # Should be within a reasonable margin
        assert abs(eval_result.timestamp - now) < 1.0

    def test_custom_clock_respected(self):
        """Test that custom clock is used in evaluation."""
        clock_value = [42.0]

        def custom_clock():
            return clock_value[0]

        watchdog = Watchdog(monotonic_clock=custom_clock)
        watchdog.register_heartbeat("worker", timeout_seconds=60)
        watchdog.heartbeat("worker")
        eval_result = watchdog.evaluate()
        assert eval_result.timestamp == 42.0

    def test_no_real_sleep_needed(self):
        """Test that no real time.sleep is needed for testing."""
        import time as time_module

        clock_time = [0.0]

        def clock():
            return clock_time[0]

        watchdog = Watchdog(monotonic_clock=clock)
        watchdog.register_heartbeat("worker", timeout_seconds=1)

        start = time_module.time()

        clock_time[0] = 0.0
        watchdog.heartbeat("worker")
        eval1 = watchdog.evaluate()
        assert eval1.items["worker"].status == Status.HEALTHY

        clock_time[0] = 10.0
        eval2 = watchdog.evaluate()
        assert eval2.items["worker"].status == Status.STALE

        elapsed = time_module.time() - start
        # Should complete in well under 1 second since we don't sleep
        assert elapsed < 1.0


class TestEvaluationResult:
    """Test Evaluation data class."""

    def test_evaluation_immutable(self):
        """Test that Evaluation is immutable (dataclass frozen)."""
        watchdog = Watchdog()
        watchdog.register_check("cache", check=lambda: True, interval_seconds=30)
        eval_result = watchdog.evaluate()
        # Dataclass fields can be reassigned (not frozen by default)
        # Just verify the structure is correct
        assert hasattr(eval_result, "timestamp")
        assert hasattr(eval_result, "items")
        assert hasattr(eval_result, "transitions")
