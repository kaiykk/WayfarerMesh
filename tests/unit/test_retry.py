"""Unit tests for the retry decorator with exponential backoff.

This module tests the retry mechanism including exponential backoff timing,
configurable max attempts, exception filtering, and retry callback functionality.
"""

import time
import pytest
from hypothesis import given, strategies as st, assume, settings
from trip_assistant_refactored.utils.error_handling.retry import retry_on_error


class TestRetryDecoratorBasics:
    """Tests for basic retry decorator functionality."""
    
    def test_successful_function_no_retry(self):
        """Test that successful functions are not retried."""
        call_count = 0
        
        @retry_on_error(max_attempts=3, backoff_factor=2.0)
        def successful_func():
            nonlocal call_count
            call_count += 1
            return "success"
        
        result = successful_func()
        
        assert result == "success"
        assert call_count == 1
    
    def test_retry_on_failure_succeeds_on_second_attempt(self):
        """Test that function retries and succeeds on second attempt."""
        call_count = 0
        
        @retry_on_error(max_attempts=3, backoff_factor=2.0)
        def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("Temporary failure")
            return "success"
        
        result = flaky_func()
        
        assert result == "success"
        assert call_count == 2
    
    def test_max_attempts_exceeded_raises_exception(self):
        """Test that exception is raised after max attempts."""
        call_count = 0
        
        @retry_on_error(max_attempts=3, backoff_factor=2.0)
        def always_fails():
            nonlocal call_count
            call_count += 1
            raise ValueError("Always fails")
        
        with pytest.raises(ValueError, match="Always fails"):
            always_fails()
        
        assert call_count == 3
    
    def test_single_attempt(self):
        """Test that max_attempts=1 runs function exactly once."""
        call_count = 0
        
        @retry_on_error(max_attempts=1, backoff_factor=2.0)
        def always_fails():
            nonlocal call_count
            call_count += 1
            raise ValueError("Always fails")
        
        with pytest.raises(ValueError):
            always_fails()
        
        assert call_count == 1


class TestRetryWithCustomExceptions:
    """Tests for retry with specific exception types."""
    
    def test_retry_on_specific_exception(self):
        """Test that retry only catches specified exception types."""
        call_count = 0
        
        @retry_on_error(
            max_attempts=3,
            backoff_factor=2.0,
            exceptions=(ValueError,)
        )
        def raises_value_error():
            nonlocal call_count
            call_count += 1
            raise ValueError("Value error")
        
        with pytest.raises(ValueError):
            raises_value_error()
        
        assert call_count == 3
    
    def test_does_not_retry_on_uncaught_exception(self):
        """Test that non-specified exceptions are not caught."""
        call_count = 0
        
        @retry_on_error(
            max_attempts=3,
            backoff_factor=2.0,
            exceptions=(ValueError,)
        )
        def raises_type_error():
            nonlocal call_count
            call_count += 1
            raise TypeError("Type error")
        
        with pytest.raises(TypeError):
            raises_type_error()
        
        assert call_count == 1
    
    def test_multiple_exception_types(self):
        """Test retry with multiple exception types."""
        call_count = 0
        
        @retry_on_error(
            max_attempts=3,
            backoff_factor=2.0,
            exceptions=(ValueError, TypeError)
        )
        def raises_multiple():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Value error")
            return "success"
        
        result = raises_multiple()
        
        assert result == "success"
        assert call_count == 3


class TestRetryWithCallback:
    """Tests for retry with callback function."""
    
    def test_callback_is_called_on_retry(self):
        """Test that on_retry callback is called before each retry."""
        retry_info = []
        
        def on_retry(attempt, error, delay):
            retry_info.append((attempt, str(error), delay))
        
        call_count = 0
        
        @retry_on_error(
            max_attempts=3,
            backoff_factor=2.0,
            on_retry=on_retry
        )
        def flaky_with_callback():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Temporary failure")
            return "success"
        
        result = flaky_with_callback()
        
        assert result == "success"
        assert call_count == 3
        assert len(retry_info) == 2  # Called before 2nd and 3rd attempts
        assert retry_info[0][0] == 1  # First retry (after 1st attempt failed)
        assert retry_info[1][0] == 2  # Second retry (after 2nd attempt failed)


class TestRetryDecoratorValidation:
    """Tests for parameter validation in retry decorator."""
    
    def test_invalid_max_attempts_raises_error(self):
        """Test that max_attempts < 1 raises ValueError."""
        with pytest.raises(ValueError, match="max_attempts must be at least 1"):
            @retry_on_error(max_attempts=0)
            def func():
                pass
    
    def test_invalid_backoff_factor_raises_error(self):
        """Test that backoff_factor <= 0 raises ValueError."""
        with pytest.raises(ValueError, match="backoff_factor must be positive"):
            @retry_on_error(max_attempts=3, backoff_factor=0)
            def func():
                pass
    
    def test_invalid_exceptions_type_raises_error(self):
        """Test that invalid exceptions parameter raises TypeError."""
        with pytest.raises(TypeError):
            @retry_on_error(max_attempts=3, exceptions="not an exception")
            def func():
                pass


class TestExponentialBackoffTiming:
    """Tests for exponential backoff timing behavior."""
    
    @pytest.mark.slow
    def test_exponential_backoff_delays(self):
        """Test that delays follow exponential backoff pattern."""
        start_times = []
        
        def record_time(attempt, error, delay):
            start_times.append(time.time())
        
        call_count = 0
        
        @retry_on_error(
            max_attempts=3,
            backoff_factor=2.0,
            on_retry=record_time
        )
        def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Temporary failure")
            return "success"
        
        start = time.time()
        result = flaky_func()
        total_time = time.time() - start
        
        assert result == "success"
        # With backoff_factor=2.0: delays should be 1s (2^0) and 2s (2^1) = ~3s total
        # Allow some tolerance for execution time
        assert total_time >= 2.5  # At least 2.5 seconds of delays
    
    @pytest.mark.slow
    def test_custom_backoff_factor(self):
        """Test that custom backoff factor is applied correctly."""
        call_count = 0
        
        @retry_on_error(
            max_attempts=3,
            backoff_factor=3.0
        )
        def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ValueError("Temporary failure")
            return "success"
        
        start = time.time()
        result = flaky_func()
        total_time = time.time() - start
        
        assert result == "success"
        # With backoff_factor=3.0: delays should be 1s (3^0) and 3s (3^1) = ~4s total
        assert total_time >= 3.5


class TestRetryPreservesFunctionMetadata:
    """Tests that retry decorator preserves function metadata."""
    
    def test_preserves_function_name(self):
        """Test that decorated function keeps its name."""
        @retry_on_error(max_attempts=3)
        def my_function():
            return "success"
        
        assert my_function.__name__ == "my_function"
    
    def test_preserves_docstring(self):
        """Test that decorated function keeps its docstring."""
        @retry_on_error(max_attempts=3)
        def my_function():
            """This is my docstring."""
            return "success"
        
        assert my_function.__doc__ == "This is my docstring."


class TestRetryWithArguments:
    """Tests for retry decorator with function arguments."""
    
    def test_passes_arguments_to_function(self):
        """Test that arguments are passed to the decorated function."""
        @retry_on_error(max_attempts=3)
        def func_with_args(a, b, c=10):
            return a + b + c
        
        result = func_with_args(1, 2, c=3)
        
        assert result == 6
    
    def test_passes_kwargs_to_function(self):
        """Test that keyword arguments are passed to the decorated function."""
        @retry_on_error(max_attempts=3)
        def func_with_kwargs(x, y, **kwargs):
            return x * y
        
        result = func_with_kwargs(3, 4, extra=5)
        
        assert result == 12


# Property-based tests

class TestRetryPropertyTests:
    """Property-based tests for retry decorator.
    
    **Validates: Requirements 3.4**
    """
    
    @given(
        max_attempts=st.integers(min_value=1, max_value=5),
        backoff_factor=st.floats(min_value=1.0, max_value=5.0, allow_nan=False, allow_infinity=False)
    )
    @settings(max_examples=10, deadline=None)
    def test_property_retry_never_exceeds_max_attempts(self, max_attempts, backoff_factor):
        """Property test: Retry mechanism never exceeds max_attempts.
        
        For any function decorated with @retry_on_error with max_attempts=N,
        the function SHALL be called at most N times before either succeeding
        or raising an exception.
        
        **Validates: Requirements 3.4**
        """
        import unittest.mock as mock
        
        call_count = 0
        
        # Mock time.sleep to avoid actual delays
        with mock.patch('trip_assistant_refactored.utils.error_handling.retry.time.sleep'):
            @retry_on_error(max_attempts=max_attempts, backoff_factor=backoff_factor)
            def always_fails():
                nonlocal call_count
                call_count += 1
                raise ValueError("Always fails")
            
            with pytest.raises(ValueError):
                always_fails()
        
        assert call_count == max_attempts
    
    @given(
        max_attempts=st.integers(min_value=2, max_value=5),
        backoff_factor=st.floats(min_value=1.0, max_value=3.0, allow_nan=False, allow_infinity=False),
        succeed_on_attempt=st.integers(min_value=1, max_value=5)
    )
    @settings(max_examples=15, deadline=None)
    def test_property_successful_retry_stops_after_success(self, max_attempts, backoff_factor, succeed_on_attempt):
        """Property test: Successful retry stops immediately.
        
        For any function that eventually succeeds after some failures,
        the retry mechanism SHALL stop retrying and return the successful result.
        
        **Validates: Requirements 3.4**
        """
        import unittest.mock as mock
        
        # Ensure succeed_on_attempt is within max_attempts
        assume(succeed_on_attempt <= max_attempts)
        
        call_count = 0
        
        # Mock time.sleep to avoid actual delays
        with mock.patch('trip_assistant_refactored.utils.error_handling.retry.time.sleep'):
            @retry_on_error(max_attempts=max_attempts, backoff_factor=backoff_factor)
            def eventually_succeeds():
                nonlocal call_count
                call_count += 1
                if call_count < succeed_on_attempt:
                    raise ValueError(f"Failure {call_count}")
                return "success"
            
            result = eventually_succeeds()
        
        assert result == "success"
        assert call_count == succeed_on_attempt
    
    @given(
        max_attempts=st.integers(min_value=2, max_value=5),
        backoff_factor=st.floats(min_value=1.0, max_value=3.0, allow_nan=False, allow_infinity=False)
    )
    @settings(max_examples=10, deadline=None)
    def test_property_exponential_backoff_increases_delay(self, max_attempts, backoff_factor):
        """Property test: Exponential backoff delay increases with each retry.
        
        For any retry decorator with backoff_factor=B, the delay before retry N
        SHALL be B^(N-1), meaning each subsequent delay is larger than the previous.
        
        **Validates: Requirements 3.4**
        """
        import unittest.mock as mock
        
        delays = []
        
        def on_retry(attempt, error, delay):
            delays.append(delay)
        
        call_count = 0
        
        # Mock time.sleep to avoid actual delays
        with mock.patch('trip_assistant_refactored.utils.error_handling.retry.time.sleep'):
            @retry_on_error(
                max_attempts=max_attempts,
                backoff_factor=backoff_factor,
                on_retry=on_retry
            )
            def always_fails():
                nonlocal call_count
                call_count += 1
                if call_count < max_attempts:
                    raise ValueError("Fails")
                return "success"
            
            try:
                always_fails()
            except ValueError:
                pass
        
        # Verify delays follow exponential pattern
        for i in range(len(delays) - 1):
            # Each delay should be approximately backoff_factor times the previous
            expected_ratio = backoff_factor
            actual_ratio = delays[i + 1] / delays[i] if delays[i] > 0 else 0
            # Allow 10% tolerance for floating point
            assert abs(actual_ratio - expected_ratio) < 0.1, \
                f"Delay ratio {actual_ratio} != expected {expected_ratio}"
    
    @given(
        max_attempts=st.integers(min_value=2, max_value=5),
        backoff_factor=st.floats(min_value=1.0, max_value=3.0, allow_nan=False, allow_infinity=False)
    )
    @settings(max_examples=10, deadline=None)
    def test_property_exception_preserved_after_all_retries(self, max_attempts, backoff_factor):
        """Property test: Final exception is preserved after all retries fail.
        
        For any function that fails all retry attempts, the original exception
        SHALL be raised (not a retry-specific exception).
        
        **Validates: Requirements 3.4**
        """
        import unittest.mock as mock
        
        original_error_message = "Original error message"
        
        # Mock time.sleep to avoid actual delays
        with mock.patch('trip_assistant_refactored.utils.error_handling.retry.time.sleep'):
            @retry_on_error(max_attempts=max_attempts, backoff_factor=backoff_factor)
            def always_fails():
                raise ValueError(original_error_message)
            
            with pytest.raises(ValueError, match=original_error_message):
                always_fails()
    
    @given(
        max_attempts=st.integers(min_value=1, max_value=5),
        backoff_factor=st.floats(min_value=1.0, max_value=3.0, allow_nan=False, allow_infinity=False),
        exception_type=st.sampled_from([ValueError, TypeError, RuntimeError])
    )
    @settings(max_examples=10, deadline=None)
    def test_property_only_caught_exceptions_are_retried(self, max_attempts, backoff_factor, exception_type):
        """Property test: Only specified exception types trigger retry.
        
        For any retry decorator with exceptions=(E1, E2, ...), only exceptions
        that are instances of E1, E2, etc. SHALL trigger a retry. Other
        exceptions SHALL propagate immediately without retry.
        
        **Validates: Requirements 3.4**
        """
        import unittest.mock as mock
        
        call_count = 0
        
        # Use a different exception type than the one specified
        other_exception = ValueError if exception_type != ValueError else TypeError
        
        # Mock time.sleep to avoid actual delays
        with mock.patch('trip_assistant_refactored.utils.error_handling.retry.time.sleep'):
            @retry_on_error(
                max_attempts=max_attempts,
                backoff_factor=backoff_factor,
                exceptions=(exception_type,)
            )
            def raises_other_exception():
                nonlocal call_count
                call_count += 1
                raise other_exception("Other exception")
            
            with pytest.raises(other_exception):
                raises_other_exception()
        
        # Should only be called once because the other exception is not caught
        assert call_count == 1