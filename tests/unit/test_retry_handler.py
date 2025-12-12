"""Tests for retry handler with exponential backoff.

Tests cover:
- Basic retry behavior
- Exponential backoff timing
- Jitter randomization
- Exception filtering
- Success on retry
- Max attempts limit
- HTTP error code detection
"""

import time
from unittest.mock import Mock, patch

import pytest

from azlin.retry_handler import (
    retry_with_exponential_backoff,
    should_retry_http_error,
)


class TestRetryWithExponentialBackoff:
    """Tests for retry_with_exponential_backoff decorator."""

    def test_success_on_first_attempt(self):
        """Test function succeeds on first attempt without retry."""
        call_count = 0

        @retry_with_exponential_backoff(max_attempts=3)
        def successful_function():
            nonlocal call_count
            call_count += 1
            return "success"

        result = successful_function()

        assert result == "success"
        assert call_count == 1

    def test_success_on_second_attempt(self):
        """Test function succeeds on second attempt after one retry."""
        call_count = 0

        @retry_with_exponential_backoff(max_attempts=3, initial_delay=0.1)
        def flaky_function():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("Transient network error")
            return "success"

        result = flaky_function()

        assert result == "success"
        assert call_count == 2

    def test_max_attempts_exceeded(self):
        """Test function fails after max attempts exceeded."""
        call_count = 0

        @retry_with_exponential_backoff(max_attempts=3, initial_delay=0.1)
        def always_fails():
            nonlocal call_count
            call_count += 1
            raise ConnectionError("Persistent error")

        with pytest.raises(ConnectionError, match="Persistent error"):
            always_fails()

        assert call_count == 3

    def test_exponential_backoff_timing(self):
        """Test delays follow exponential backoff pattern."""
        call_times = []

        @retry_with_exponential_backoff(
            max_attempts=4, initial_delay=0.1, jitter=False
        )
        def failing_function():
            call_times.append(time.time())
            raise TimeoutError("Network timeout")

        with pytest.raises(TimeoutError):
            failing_function()

        # Verify we have 4 attempts
        assert len(call_times) == 4

        # Calculate delays between attempts
        delays = [call_times[i + 1] - call_times[i] for i in range(len(call_times) - 1)]

        # Verify exponential backoff (1x, 2x, 4x)
        # Allow 10% tolerance for timing variance
        assert delays[0] == pytest.approx(0.1, rel=0.1)  # 0.1s delay
        assert delays[1] == pytest.approx(0.2, rel=0.1)  # 0.2s delay (2x)
        assert delays[2] == pytest.approx(0.4, rel=0.1)  # 0.4s delay (4x)

    def test_max_delay_cap(self):
        """Test delays are capped at max_delay."""
        call_times = []

        @retry_with_exponential_backoff(
            max_attempts=4,
            initial_delay=10.0,
            max_delay=0.2,  # Cap at 0.2s
            jitter=False,
        )
        def failing_function():
            call_times.append(time.time())
            raise ConnectionError("Error")

        with pytest.raises(ConnectionError):
            failing_function()

        # Calculate delays
        delays = [call_times[i + 1] - call_times[i] for i in range(len(call_times) - 1)]

        # All delays should be capped at max_delay (0.2s)
        for delay in delays:
            assert delay <= 0.3  # 0.2s + tolerance

    def test_jitter_randomization(self):
        """Test jitter adds randomness to delays."""
        delays_run1 = []
        delays_run2 = []

        def measure_delays():
            call_times = []

            @retry_with_exponential_backoff(
                max_attempts=3, initial_delay=0.2, jitter=True
            )
            def failing_function():
                call_times.append(time.time())
                raise ConnectionError("Error")

            try:
                failing_function()
            except ConnectionError:
                pass

            return [call_times[i + 1] - call_times[i] for i in range(len(call_times) - 1)]

        delays_run1 = measure_delays()
        delays_run2 = measure_delays()

        # With jitter, delays should be different between runs
        # (extremely unlikely to be identical with random jitter)
        assert delays_run1 != delays_run2

    def test_custom_retryable_exceptions(self):
        """Test custom exception types for retry."""

        class CustomError(Exception):
            pass

        call_count = 0

        @retry_with_exponential_backoff(
            max_attempts=3,
            initial_delay=0.1,
            retryable_exceptions=(CustomError,),
        )
        def function_with_custom_error():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise CustomError("Transient custom error")
            return "success"

        result = function_with_custom_error()

        assert result == "success"
        assert call_count == 2

    def test_non_retryable_exception(self):
        """Test non-retryable exception is not retried."""
        call_count = 0

        @retry_with_exponential_backoff(
            max_attempts=3,
            retryable_exceptions=(ConnectionError,),
        )
        def function_with_value_error():
            nonlocal call_count
            call_count += 1
            raise ValueError("Non-retryable error")

        with pytest.raises(ValueError, match="Non-retryable error"):
            function_with_value_error()

        # Should fail immediately without retry
        assert call_count == 1

    def test_function_with_arguments(self):
        """Test decorator works with functions that take arguments."""
        call_count = 0

        @retry_with_exponential_backoff(max_attempts=3, initial_delay=0.1)
        def function_with_args(x, y, *, z=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("Error")
            return x + y + (z or 0)

        result = function_with_args(1, 2, z=3)

        assert result == 6
        assert call_count == 2

    def test_preserves_function_metadata(self):
        """Test decorator preserves function name and docstring."""

        @retry_with_exponential_backoff(max_attempts=3)
        def documented_function():
            """This is a documented function."""
            return "result"

        assert documented_function.__name__ == "documented_function"
        assert documented_function.__doc__ == "This is a documented function."

    @patch("azlin.retry_handler.logger")
    def test_logging_on_retry(self, mock_logger):
        """Test retry attempts are logged."""
        call_count = 0

        @retry_with_exponential_backoff(max_attempts=3, initial_delay=0.1)
        def flaky_function():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("Transient error")
            return "success"

        flaky_function()

        # Should log warning on retry
        assert mock_logger.warning.called
        warning_msg = mock_logger.warning.call_args[0][0]
        assert "attempt 1/3" in warning_msg
        assert "retrying in" in warning_msg

    @patch("azlin.retry_handler.logger")
    def test_logging_on_final_failure(self, mock_logger):
        """Test final failure is logged as error."""

        @retry_with_exponential_backoff(max_attempts=2, initial_delay=0.1)
        def always_fails():
            raise ConnectionError("Persistent error")

        with pytest.raises(ConnectionError):
            always_fails()

        # Should log error after max attempts
        assert mock_logger.error.called
        error_msg = mock_logger.error.call_args[0][0]
        assert "failed after 2 attempts" in error_msg


class TestShouldRetryHttpError:
    """Tests for HTTP error code retry detection."""

    def test_retryable_status_codes(self):
        """Test status codes that should trigger retry."""
        retryable_codes = [408, 429, 500, 502, 503, 504]

        for code in retryable_codes:
            assert should_retry_http_error(code), f"Status {code} should be retryable"

    def test_non_retryable_status_codes(self):
        """Test status codes that should NOT trigger retry."""
        non_retryable_codes = [
            200,  # OK
            201,  # Created
            400,  # Bad Request
            401,  # Unauthorized
            403,  # Forbidden
            404,  # Not Found
            405,  # Method Not Allowed
        ]

        for code in non_retryable_codes:
            assert not should_retry_http_error(code), f"Status {code} should not be retryable"


class TestAzureExceptionRetry:
    """Tests for Azure SDK exception retry behavior."""

    def test_azure_http_response_error_retry(self):
        """Test Azure HttpResponseError triggers retry."""
        try:
            from azure.core.exceptions import HttpResponseError

            call_count = 0

            @retry_with_exponential_backoff(max_attempts=3, initial_delay=0.1)
            def function_with_azure_error():
                nonlocal call_count
                call_count += 1
                if call_count < 2:
                    # Create mock response
                    mock_response = Mock()
                    mock_response.status_code = 429
                    raise HttpResponseError(message="Too Many Requests", response=mock_response)
                return "success"

            result = function_with_azure_error()

            assert result == "success"
            assert call_count == 2

        except ImportError:
            pytest.skip("Azure SDK not available")

    def test_azure_service_request_error_retry(self):
        """Test Azure ServiceRequestError triggers retry."""
        try:
            from azure.core.exceptions import ServiceRequestError

            call_count = 0

            @retry_with_exponential_backoff(max_attempts=3, initial_delay=0.1)
            def function_with_service_error():
                nonlocal call_count
                call_count += 1
                if call_count < 2:
                    raise ServiceRequestError("Network error")
                return "success"

            result = function_with_service_error()

            assert result == "success"
            assert call_count == 2

        except ImportError:
            pytest.skip("Azure SDK not available")


class TestSubprocessTimeoutRetry:
    """Tests for subprocess timeout retry behavior."""

    def test_subprocess_timeout_retry(self):
        """Test subprocess.TimeoutExpired triggers retry."""
        import subprocess

        call_count = 0

        @retry_with_exponential_backoff(max_attempts=3, initial_delay=0.1)
        def function_with_timeout():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise subprocess.TimeoutExpired("cmd", timeout=30)
            return "success"

        result = function_with_timeout()

        assert result == "success"
        assert call_count == 2
