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

        # Frozen dataclass: cannot assign to fields
        with pytest.raises(AttributeError):
            eval_result.timestamp = 100.0

        with pytest.raises(AttributeError):
            eval_result.items = {}

        with pytest.raises(AttributeError):
            eval_result.transitions = ()

    def test_items_read_only_mapping(self):
        """Test that items is a read-only mapping (MappingProxyType)."""
        watchdog = Watchdog()
        watchdog.register_check("cache", check=lambda: True, interval_seconds=30)
        eval_result = watchdog.evaluate()

        # Cannot assign to the items dict
        with pytest.raises(TypeError):
            eval_result.items["new_key"] = None

    def test_transitions_immutable_tuple(self):
        """Test that transitions is an immutable tuple."""
        watchdog = Watchdog()
        watchdog.register_heartbeat("worker", timeout_seconds=1)
        clock = [0.0]
        watchdog_clock = Watchdog(monotonic_clock=lambda: clock[0])
        watchdog_clock.register_heartbeat("worker", timeout_seconds=1)

        clock[0] = 0.0
        watchdog_clock.heartbeat("worker")
        eval1 = watchdog_clock.evaluate()

        # transitions should be a tuple (immutable)
        assert isinstance(eval1.transitions, tuple)

        # Cannot append to tuple
        with pytest.raises(AttributeError):
            eval1.transitions.append(None)


class TestIntervalValidation:
    """Test strictness of interval validation."""

    def test_reject_nan_timeout(self):
        """Test that NaN timeout is rejected."""
        watchdog = Watchdog()
        with pytest.raises(InvalidIntervalError):
            watchdog.register_heartbeat("worker", timeout_seconds=float("nan"))

    def test_reject_inf_timeout(self):
        """Test that infinity timeout is rejected."""
        watchdog = Watchdog()
        with pytest.raises(InvalidIntervalError):
            watchdog.register_heartbeat("worker", timeout_seconds=float("inf"))

    def test_reject_nan_interval(self):
        """Test that NaN interval is rejected."""
        watchdog = Watchdog()
        with pytest.raises(InvalidIntervalError):
            watchdog.register_check(
                "cache", check=lambda: True, interval_seconds=float("nan")
            )

    def test_reject_inf_interval(self):
        """Test that infinity interval is rejected."""
        watchdog = Watchdog()
        with pytest.raises(InvalidIntervalError):
            watchdog.register_check(
                "cache", check=lambda: True, interval_seconds=float("inf")
            )

    def test_reject_bool_timeout(self):
        """Test that boolean timeout is rejected."""
        watchdog = Watchdog()
        with pytest.raises(InvalidIntervalError):
            watchdog.register_heartbeat("worker", timeout_seconds=True)

    def test_reject_bool_interval(self):
        """Test that boolean interval is rejected."""
        watchdog = Watchdog()
        with pytest.raises(InvalidIntervalError):
            watchdog.register_check(
                "cache", check=lambda: True, interval_seconds=False
            )

    def test_accept_positive_int(self):
        """Test that positive int is accepted for interval."""
        watchdog = Watchdog()
        watchdog.register_check("cache", check=lambda: True, interval_seconds=30)
        # Should not raise

    def test_accept_positive_float(self):
        """Test that positive float is accepted for timeout."""
        watchdog = Watchdog()
        watchdog.register_heartbeat("worker", timeout_seconds=60.5)
        # Should not raise


class TestCheckReturnType:
    """Test strict bool return type validation for health checks."""

    def test_check_returns_string_fails(self):
        """Test that check returning string is marked failed."""
        watchdog = Watchdog()
        watchdog.register_check("cache", check=lambda: "yes", interval_seconds=30)
        eval_result = watchdog.evaluate()
        assert eval_result.items["cache"].status == Status.FAILED
        assert "Check must return bool" in eval_result.items["cache"].last_error

    def test_check_returns_int_fails(self):
        """Test that check returning int is marked failed."""
        watchdog = Watchdog()
        watchdog.register_check("cache", check=lambda: 1, interval_seconds=30)
        eval_result = watchdog.evaluate()
        assert eval_result.items["cache"].status == Status.FAILED
        assert "Check must return bool" in eval_result.items["cache"].last_error

    def test_check_returns_none_fails(self):
        """Test that check returning None is marked failed."""
        watchdog = Watchdog()
        watchdog.register_check("cache", check=lambda: None, interval_seconds=30)
        eval_result = watchdog.evaluate()
        assert eval_result.items["cache"].status == Status.FAILED
        assert "Check must return bool" in eval_result.items["cache"].last_error

    def test_check_returns_list_fails(self):
        """Test that check returning list is marked failed."""
        watchdog = Watchdog()
        watchdog.register_check("cache", check=list, interval_seconds=30)
        eval_result = watchdog.evaluate()
        assert eval_result.items["cache"].status == Status.FAILED
        assert "Check must return bool" in eval_result.items["cache"].last_error

    def test_check_returns_true_succeeds(self):
        """Test that check returning True is healthy."""
        watchdog = Watchdog()
        watchdog.register_check("cache", check=lambda: True, interval_seconds=30)
        eval_result = watchdog.evaluate()
        assert eval_result.items["cache"].status == Status.HEALTHY

    def test_check_returns_false_fails(self):
        """Test that check returning False is failed."""
        watchdog = Watchdog()
        watchdog.register_check("cache", check=lambda: False, interval_seconds=30)
        eval_result = watchdog.evaluate()
        assert eval_result.items["cache"].status == Status.FAILED


class TestErrorTextBounding:
    """Test error text truncation with various exception names."""

    def test_error_text_with_long_exception_name(self):
        """Test that error text is bounded even with long exception class name."""
        watchdog = Watchdog()

        class VeryLongExceptionNameThatIsReallyQuiteLongIndeed(Exception):
            pass

        def bad_check():
            raise VeryLongExceptionNameThatIsReallyQuiteLongIndeed(
                "this is a very long error message that might exceed the truncation limit"
            )

        watchdog.register_check("service", check=bad_check, interval_seconds=30)
        eval_result = watchdog.evaluate()

        # Error text should be truncated and fit within reasonable bounds
        error = eval_result.items["service"].last_error
        assert error is not None
        assert len(error) <= 120  # Original limit
        assert "VeryLongExceptionNameThatIsReallyQuiteLongIndeed" in error

    def test_error_text_truncation_normal_case(self):
        """Test error text truncation in normal case."""
        watchdog = Watchdog()

        def bad_check():
            raise ValueError("a" * 200)  # Very long message

        watchdog.register_check("service", check=bad_check, interval_seconds=30)
        eval_result = watchdog.evaluate()

        error = eval_result.items["service"].last_error
        assert error is not None
        assert len(error) <= 120
        assert error.startswith("ValueError:")


class TestCheckSchedulingSemantics:
    """Test that checks use eager evaluation, not interval-based scheduling."""

    def test_check_runs_on_every_evaluate(self):
        """Test that check is run on every evaluate() call, not throttled by interval."""
        watchdog = Watchdog()
        call_count = [0]

        def counting_check():
            call_count[0] += 1
            return True

        # Register with 30-second interval
        watchdog.register_check("cache", check=counting_check, interval_seconds=30)

        # First evaluate
        watchdog.evaluate()
        assert call_count[0] == 1

        # Second evaluate immediately after (within interval)
        watchdog.evaluate()
        assert call_count[0] == 2  # Check was run again, not throttled

        # Third evaluate
        watchdog.evaluate()
        assert call_count[0] == 3

    def test_interval_seconds_is_metadata_only(self):
        """Test that interval_seconds parameter doesn't control execution frequency."""
        watchdog = Watchdog()
        call_count = [0]

        def counting_check():
            call_count[0] += 1
            return True

        # Register with very large interval (should not prevent execution)
        watchdog.register_check(
            "service", check=counting_check, interval_seconds=999999
        )

        watchdog.evaluate()
        watchdog.evaluate()

        # Both evaluate() calls should have run the check
        assert call_count[0] == 2

    def test_last_check_time_updated_on_every_evaluate(self):
        """Test that last_check_time is updated on every evaluate() call."""
        clock_time = [0.0]

        def clock():
            return clock_time[0]

        watchdog = Watchdog(monotonic_clock=clock)
        watchdog.register_check("cache", check=lambda: True, interval_seconds=30)

        clock_time[0] = 10.0
        eval1 = watchdog.evaluate()
        assert eval1.items["cache"].last_check_time == 10.0

        clock_time[0] = 20.0
        eval2 = watchdog.evaluate()
        assert eval2.items["cache"].last_check_time == 20.0

        clock_time[0] = 25.0
        eval3 = watchdog.evaluate()
        assert eval3.items["cache"].last_check_time == 25.0


class TestConcurrentSafety:
    """Test concurrent safety and lock scope."""

    def test_blocking_check_does_not_block_heartbeat(self):
        """Test that slow check callbacks don't block heartbeat recording."""
        import threading

        clock_time = [0.0]

        def clock():
            return clock_time[0]

        watchdog = Watchdog(monotonic_clock=clock)
        watchdog.register_check(
            "slow_check", check=lambda: True, interval_seconds=30
        )
        watchdog.register_heartbeat("worker", timeout_seconds=60)

        check_called = threading.Event()
        check_done = threading.Event()
        heartbeat_recorded = threading.Event()

        def slow_check():
            check_called.set()
            # Simulate slow callback (would block if callback ran inside lock)
            check_done.wait(timeout=1.0)
            return True

        # Replace the check with slow version
        watchdog._checks["slow_check"]["check"] = slow_check

        results = []

        def evaluate_thread():
            results.append(watchdog.evaluate())

        def heartbeat_thread():
            check_called.wait(timeout=1.0)
            # Record heartbeat while check is still running
            watchdog.heartbeat("worker")
            heartbeat_recorded.set()
            check_done.set()

        # Set initial clock time
        clock_time[0] = 10.0

        eval_t = threading.Thread(target=evaluate_thread)
        beat_t = threading.Thread(target=heartbeat_thread)

        eval_t.start()
        beat_t.start()

        # Simulate time passing during slow check execution
        import time

        time.sleep(0.01)
        clock_time[0] = 15.0

        eval_t.join(timeout=5.0)
        beat_t.join(timeout=5.0)

        # Heartbeat should have been recorded despite slow check
        assert heartbeat_recorded.is_set()
        assert len(results) == 1
        # The evaluation happened after heartbeat was recorded
        assert results[0].items["worker"].last_heartbeat is not None

    def test_timestamp_ordering_consistency(self):
        """Test that evaluation timestamp is consistent with recorded heartbeat times."""
        clock_time = [0.0]

        def clock():
            return clock_time[0]

        watchdog = Watchdog(monotonic_clock=clock)
        watchdog.register_heartbeat("worker", timeout_seconds=60)

        clock_time[0] = 10.0
        watchdog.heartbeat("worker")

        clock_time[0] = 20.0
        eval_result = watchdog.evaluate()

        # The evaluation was at 20.0, heartbeat was at 10.0
        # So heartbeat should be considered healthy (within 60s)
        assert eval_result.items["worker"].status == Status.HEALTHY
        assert eval_result.items["worker"].last_heartbeat == 10.0
        assert eval_result.timestamp == 20.0

        # Now move beyond timeout
        clock_time[0] = 75.0
        eval_result2 = watchdog.evaluate()
        assert eval_result2.items["worker"].status == Status.STALE

    def test_heartbeat_during_callback_not_unknown(self):
        """Regression test: heartbeat recorded during callback should not be UNKNOWN.

        This tests the fix for the concurrent heartbeat timestamp race:
        - evaluate() samples current_time at Phase 1 start
        - callback blocks outside lock during Phase 2
        - heartbeat is recorded during Phase 2 (timestamp later than Phase 1 sample)
        - Phase 3 re-samples clock and uses final_time for heartbeat evaluation
        - heartbeat should be HEALTHY (not UNKNOWN due to negative elapsed time)
        """
        import threading

        clock_time = [0.0]

        def clock():
            return clock_time[0]

        watchdog = Watchdog(monotonic_clock=clock)

        # Register a slow check and heartbeat
        check_started = threading.Event()
        check_finish = threading.Event()

        def slow_check():
            check_started.set()
            check_finish.wait(timeout=5.0)
            return True

        watchdog.register_check("slow", check=slow_check, interval_seconds=30)
        watchdog.register_heartbeat("worker", timeout_seconds=60)

        # Record initial heartbeat before evaluation
        clock_time[0] = 5.0
        watchdog.heartbeat("worker")

        results = []

        def evaluate_thread():
            clock_time[0] = 10.0  # Evaluation starts at t=10.0
            results.append(watchdog.evaluate())

        def heartbeat_thread():
            # Wait for check to start blocking
            check_started.wait(timeout=5.0)
            # Record heartbeat at t=15.0 (after evaluation Phase 1 sample)
            clock_time[0] = 15.0
            watchdog.heartbeat("worker")
            # Let check complete
            check_finish.set()

        eval_t = threading.Thread(target=evaluate_thread)
        beat_t = threading.Thread(target=heartbeat_thread)

        eval_t.start()
        beat_t.start()

        eval_t.join(timeout=5.0)
        beat_t.join(timeout=5.0)

        # Heartbeat should be HEALTHY, not UNKNOWN
        # (before fix: would be UNKNOWN due to negative elapsed time)
        assert len(results) == 1
        assert results[0].items["worker"].status == Status.HEALTHY
        assert results[0].items["worker"].last_heartbeat == 15.0
        # Evaluation timestamp should be at or after the heartbeat was recorded
        assert results[0].timestamp >= 15.0

    def test_callback_exception_does_not_affect_other_checks(self):
        """Test that one check exception doesn't affect other check execution."""
        watchdog = Watchdog()

        def failing_check():
            raise RuntimeError("check failed")

        def passing_check():
            return True

        watchdog.register_check("bad", check=failing_check, interval_seconds=30)
        watchdog.register_check("good", check=passing_check, interval_seconds=30)

        eval_result = watchdog.evaluate()

        # Both should be evaluated despite one failing
        assert eval_result.items["bad"].status == Status.FAILED
        assert eval_result.items["bad"].last_error is not None
        assert eval_result.items["good"].status == Status.HEALTHY
        assert eval_result.items["good"].last_error is None


class TestMalformedNumericInput:
    """Test handling of malformed numeric input."""

    def test_reject_string_interval(self):
        """Test that string timeout is rejected."""
        watchdog = Watchdog()
        with pytest.raises(InvalidIntervalError):
            watchdog.register_heartbeat("worker", timeout_seconds="60")  # type: ignore

    def test_reject_none_interval(self):
        """Test that None interval is rejected."""
        watchdog = Watchdog()
        with pytest.raises(InvalidIntervalError):
            watchdog.register_heartbeat("worker", timeout_seconds=None)  # type: ignore

    def test_reject_negative_interval(self):
        """Test that negative interval is rejected."""
        watchdog = Watchdog()
        with pytest.raises(InvalidIntervalError):
            watchdog.register_heartbeat("worker", timeout_seconds=-1.0)

    def test_reject_zero_interval(self):
        """Test that zero interval is rejected."""
        watchdog = Watchdog()
        with pytest.raises(InvalidIntervalError):
            watchdog.register_heartbeat("worker", timeout_seconds=0.0)


class TestBoundedHistoryEviction:
    """Test that history is actually bounded and old events evicted."""

    def test_history_truly_bounded_at_max(self):
        """Test that history is capped at MAX_HISTORY_EVENTS."""
        clock_time = [0.0]

        def clock():
            return clock_time[0]

        watchdog = Watchdog(monotonic_clock=clock)
        watchdog.register_heartbeat("hb", timeout_seconds=1)

        # Generate enough transitions to exceed MAX_HISTORY_EVENTS
        # Each heartbeat + state change can generate a transition
        # We need to create enough state changes
        for i in range(watchdog.MAX_HISTORY_EVENTS + 100):
            clock_time[0] = i * 2.0
            if i % 2 == 0:
                watchdog.heartbeat("hb")
            else:
                # Skip heartbeat to create STALE -> UNKNOWN transitions
                pass
            watchdog.evaluate()

        history = watchdog.get_history()
        # History should be bounded at MAX_HISTORY_EVENTS
        assert len(history) <= watchdog.MAX_HISTORY_EVENTS
        # Should have exactly MAX_HISTORY_EVENTS (deque is full)
        assert len(history) == watchdog.MAX_HISTORY_EVENTS

    def test_oldest_events_actually_removed(self):
        """Test that oldest transitions are removed when limit exceeded."""
        clock_time = [0.0]

        def clock():
            return clock_time[0]

        watchdog = Watchdog(monotonic_clock=clock)
        watchdog.register_heartbeat("hb", timeout_seconds=1)

        # Generate first transition at time 0
        clock_time[0] = 0.0
        watchdog.heartbeat("hb")
        eval1 = watchdog.evaluate()
        first_timestamp = eval1.transitions[0].timestamp if eval1.transitions else None

        # Generate many transitions to exceed MAX_HISTORY_EVENTS
        for i in range(watchdog.MAX_HISTORY_EVENTS + 100):
            clock_time[0] = 100 + i * 2.0
            if i % 2 == 0:
                watchdog.heartbeat("hb")
            watchdog.evaluate()

        history = watchdog.get_history()
        # The oldest event should NOT be the first one we created
        # (it should have been evicted)
        if first_timestamp is not None and len(history) > 0:
            assert history[0].timestamp > first_timestamp
