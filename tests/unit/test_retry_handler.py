"""Tests for retry handler with rate limiting integration."""

import time
from unittest.mock import Mock, patch

import pytest

from azlin.retry_handler import (
    retry_with_exponential_backoff,
    should_retry_http_error,
)


class TestShouldRetryHttpError:
    """Tests for should_retry_http_error()."""

    def test_returns_true_for_408_request_timeout(self):
        """Should retry on 408 Request Timeout."""
        assert should_retry_http_error(408) is True

    def test_returns_true_for_429_rate_limit(self):
        """Should retry on 429 Too Many Requests."""
        assert should_retry_http_error(429) is True

    def test_returns_true_for_500_internal_server_error(self):
        """Should retry on 500 Internal Server Error."""
        assert should_retry_http_error(500) is True

    def test_returns_true_for_502_bad_gateway(self):
        """Should retry on 502 Bad Gateway."""
        assert should_retry_http_error(502) is True

    def test_returns_true_for_503_service_unavailable(self):
        """Should retry on 503 Service Unavailable."""
        assert should_retry_http_error(503) is True

    def test_returns_true_for_504_gateway_timeout(self):
        """Should retry on 504 Gateway Timeout."""
        assert should_retry_http_error(504) is True

    def test_returns_false_for_400_bad_request(self):
        """Should not retry on 400 Bad Request."""
        assert should_retry_http_error(400) is False

    def test_returns_false_for_404_not_found(self):
        """Should not retry on 404 Not Found."""
        assert should_retry_http_error(404) is False


class TestRetryWithExponentialBackoff:
    """Tests for retry_with_exponential_backoff decorator."""

    def test_succeeds_on_first_attempt(self):
        """Should return immediately on success."""
        call_count = 0

        @retry_with_exponential_backoff(max_attempts=3)
        def successful_operation():
            nonlocal call_count
            call_count += 1
            return "success"

        result = successful_operation()

        assert result == "success"
        assert call_count == 1

    def test_retries_on_transient_error(self):
        """Should retry on transient errors."""
        call_count = 0

        @retry_with_exponential_backoff(max_attempts=3, initial_delay=0.01, jitter=False)
        def flaky_operation():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Temporary network error")
            return "success"

        result = flaky_operation()

        assert result == "success"
        assert call_count == 3

    def test_raises_after_max_attempts(self):
        """Should raise exception after max attempts exceeded."""
        call_count = 0

        @retry_with_exponential_backoff(max_attempts=3, initial_delay=0.01, jitter=False)
        def always_fails():
            nonlocal call_count
            call_count += 1
            raise ConnectionError("Always fails")

        with pytest.raises(ConnectionError, match="Always fails"):
            always_fails()

        assert call_count == 3

    def test_exponential_backoff_delays(self):
        """Should use exponential backoff between retries."""
        call_count = 0
        call_times = []

        @retry_with_exponential_backoff(max_attempts=4, initial_delay=0.05, jitter=False)
        def flaky_operation():
            nonlocal call_count
            call_count += 1
            call_times.append(time.time())
            if call_count < 4:
                raise ConnectionError("Retry me")
            return "success"

        result = flaky_operation()

        assert result == "success"
        assert call_count == 4

        # Check delays: 0.05s, 0.1s, 0.2s
        delays = [call_times[i] - call_times[i - 1] for i in range(1, len(call_times))]
        assert delays[0] >= 0.04  # ~0.05s
        assert delays[1] >= 0.08  # ~0.1s
        assert delays[2] >= 0.15  # ~0.2s

    def test_jitter_adds_randomness(self):
        """Should add jitter to delays when enabled."""
        call_count = 0
        delays = []

        @retry_with_exponential_backoff(max_attempts=3, initial_delay=1.0, jitter=True)
        def flaky_operation():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                # Mock time to capture delay
                raise ConnectionError("Retry me")
            return "success"

        # We can't easily test jitter directly, but verify it completes
        with patch("time.sleep") as mock_sleep:
            result = flaky_operation()

            assert result == "success"
            assert mock_sleep.call_count == 2  # 2 retries
            # Delays should have some variation (not exact)
            delays = [call[0][0] for call in mock_sleep.call_args_list]
            # First delay should be ~1.0 ± 25%
            assert 0.7 <= delays[0] <= 1.3


class MockRateLimitError(Exception):
    """Mock exception that mimics Azure HttpResponseError."""

    def __init__(self, status_code, retry_after=None):
        self.status_code = status_code
        self.response = Mock()
        self.response.headers = {}
        if retry_after:
            self.response.headers["Retry-After"] = retry_after
        super().__init__(f"Rate limit error: {status_code}")


class TestRateLimitingIntegration:
    """Tests for rate limiting integration with retry handler."""

    def test_handles_429_with_retry_after_header(self):
        """Should respect Retry-After header for 429 errors."""
        call_count = 0
        sleep_times = []

        @retry_with_exponential_backoff(
            max_attempts=3,
            initial_delay=1.0,
            retryable_exceptions=(MockRateLimitError,),
        )
        def rate_limited_operation():
            nonlocal call_count
            call_count += 1

            if call_count == 1:
                # First call: rate limited with Retry-After
                raise MockRateLimitError(429, retry_after="0.1")

            return "success"

        with patch("time.sleep") as mock_sleep:
            result = rate_limited_operation()

            assert result == "success"
            assert call_count == 2

            # Should have slept for Retry-After duration
            mock_sleep.assert_called()
            sleep_times = [call[0][0] for call in mock_sleep.call_args_list]
            assert sleep_times[0] == 0.1  # Retry-After value

    def test_handles_429_without_retry_after_header(self):
        """Should use default backoff for 429 without Retry-After."""
        call_count = 0

        @retry_with_exponential_backoff(
            max_attempts=3,
            initial_delay=0.05,
            jitter=False,
            retryable_exceptions=(MockRateLimitError,),
        )
        def rate_limited_operation():
            nonlocal call_count
            call_count += 1

            if call_count == 1:
                # Rate limited without Retry-After
                raise MockRateLimitError(429)

            return "success"

        with patch("time.sleep") as mock_sleep:
            result = rate_limited_operation()

            assert result == "success"
            assert call_count == 2
            # Should have used initial_delay as fallback
            mock_sleep.assert_called()

    def test_first_rate_limit_does_not_count_against_attempts(self):
        """Should not count first rate limit against max_attempts."""
        call_count = 0

        @retry_with_exponential_backoff(
            max_attempts=2,
            initial_delay=0.01,
            retryable_exceptions=(MockRateLimitError, ConnectionError),
        )
        def rate_limited_operation():
            nonlocal call_count
            call_count += 1

            if call_count == 1:
                # First call: rate limited
                raise MockRateLimitError(429, retry_after="0.01")
            if call_count == 2:
                # Second call: still fails (non-rate-limit)
                raise ConnectionError("Network error")

            return "success"

        # Should get 3 attempts total: 1 rate limit + 2 regular attempts
        with patch("time.sleep"):
            result = rate_limited_operation()
            assert result == "success"
            assert call_count == 3

    def test_consecutive_rate_limits(self):
        """Should handle consecutive rate limit errors."""
        call_count = 0
        retry_after_values = ["0.05", "0.1", "0.15"]

        @retry_with_exponential_backoff(
            max_attempts=5,
            initial_delay=0.01,
            retryable_exceptions=(MockRateLimitError,),
        )
        def rate_limited_operation():
            nonlocal call_count
            call_count += 1

            if call_count <= 3:
                # Consecutive rate limits
                raise MockRateLimitError(429, retry_after=retry_after_values[call_count - 1])

            return "success"

        with patch("time.sleep") as mock_sleep:
            result = rate_limited_operation()

            assert result == "success"
            assert call_count == 4

            # Should have respected all Retry-After values
            sleep_calls = [call[0][0] for call in mock_sleep.call_args_list]
            assert sleep_calls[0] == 0.05
            assert sleep_calls[1] == 0.1
            assert sleep_calls[2] == 0.15


class TestCustomRetryableExceptions:
    """Tests for custom retryable exceptions."""

    def test_retries_custom_exceptions(self):
        """Should retry custom exception types."""
        call_count = 0

        class CustomError(Exception):
            pass

        @retry_with_exponential_backoff(
            max_attempts=3,
            initial_delay=0.01,
            retryable_exceptions=(CustomError,),
        )
        def custom_operation():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise CustomError("Custom error")
            return "success"

        result = custom_operation()

        assert result == "success"
        assert call_count == 3

    def test_does_not_retry_non_retryable_exceptions(self):
        """Should not retry non-retryable exceptions."""
        call_count = 0

        @retry_with_exponential_backoff(max_attempts=3, retryable_exceptions=(ConnectionError,))
        def mixed_operation():
            nonlocal call_count
            call_count += 1
            raise ValueError("Not retryable")

        with pytest.raises(ValueError, match="Not retryable"):
            mixed_operation()

        assert call_count == 1  # Should not have retried


class TestMaxDelayEnforcement:
    """Tests for max_delay enforcement."""

    def test_caps_delay_at_max_delay(self):
        """Should cap delay at max_delay."""
        call_count = 0

        @retry_with_exponential_backoff(
            max_attempts=5, initial_delay=10.0, max_delay=15.0, jitter=False
        )
        def flaky_operation():
            nonlocal call_count
            call_count += 1
            if call_count < 5:
                raise ConnectionError("Retry me")
            return "success"

        with patch("time.sleep") as mock_sleep:
            result = flaky_operation()

            assert result == "success"
            sleep_calls = [call[0][0] for call in mock_sleep.call_args_list]

            # Delays should be: 10, 15 (capped), 15 (capped), 15 (capped)
            assert sleep_calls[0] == 10.0
            assert sleep_calls[1] == 15.0  # Capped from 20
            assert sleep_calls[2] == 15.0  # Capped from 40
            assert sleep_calls[3] == 15.0  # Capped from 80
