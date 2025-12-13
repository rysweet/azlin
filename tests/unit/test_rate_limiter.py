"""Tests for rate limiting detection and handling."""

import time
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from unittest.mock import Mock

from azlin.rate_limiter import (
    MAX_RETRY_AFTER_SECONDS,
    extract_retry_after,
    handle_rate_limit_error,
    is_rate_limit_error,
    parse_retry_after,
    wait_for_rate_limit,
)


class TestIsRateLimitError:
    """Tests for is_rate_limit_error()."""

    def test_detects_429_status_code_attribute(self):
        """Should detect error with status_code = 429."""
        error = Mock()
        error.status_code = 429

        assert is_rate_limit_error(error) is True

    def test_detects_429_response_status_code(self):
        """Should detect error with response.status_code = 429."""
        error = Mock()
        error.response = Mock()
        error.response.status_code = 429

        assert is_rate_limit_error(error) is True

    def test_returns_false_for_non_429_status(self):
        """Should return False for non-429 status codes."""
        error = Mock()
        error.status_code = 500

        assert is_rate_limit_error(error) is False

    def test_returns_false_for_error_without_status(self):
        """Should return False for errors without status code."""
        error = ValueError("Some error")

        assert is_rate_limit_error(error) is False


class TestParseRetryAfter:
    """Tests for parse_retry_after()."""

    def test_parses_integer_seconds(self):
        """Should parse integer seconds format."""
        result = parse_retry_after("60")

        assert result == 60.0

    def test_parses_float_seconds(self):
        """Should parse float seconds format."""
        result = parse_retry_after("120.5")

        assert result == 120.5

    def test_parses_http_date_format(self):
        """Should parse HTTP date format."""
        # Create a time 60 seconds in the future
        future_time = datetime.now(UTC) + timedelta(seconds=60)
        http_date = format_datetime(future_time)

        result = parse_retry_after(http_date)

        # Should be approximately 60 seconds (allow small tolerance)
        assert 58 <= result <= 62

    def test_caps_at_max_retry_after(self):
        """Should cap wait time at MAX_RETRY_AFTER_SECONDS."""
        result = parse_retry_after("9999")

        assert result == MAX_RETRY_AFTER_SECONDS

    def test_returns_zero_for_none(self):
        """Should return 0 for None value."""
        result = parse_retry_after(None)

        assert result == 0.0

    def test_returns_zero_for_empty_string(self):
        """Should return 0 for empty string."""
        result = parse_retry_after("")

        assert result == 0.0

    def test_returns_zero_for_invalid_format(self):
        """Should return 0 for unparseable format."""
        result = parse_retry_after("invalid")

        assert result == 0.0

    def test_returns_zero_for_past_http_date(self):
        """Should return 0 for HTTP dates in the past."""
        # Create a time in the past
        past_time = datetime.now(UTC) - timedelta(seconds=60)
        http_date = format_datetime(past_time)

        result = parse_retry_after(http_date)

        assert result == 0.0


class TestExtractRetryAfter:
    """Tests for extract_retry_after()."""

    def test_extracts_retry_after_from_headers(self):
        """Should extract Retry-After from response headers."""
        error = Mock()
        error.response = Mock()
        error.response.headers = {"Retry-After": "120"}

        result = extract_retry_after(error)

        assert result == 120.0

    def test_handles_case_insensitive_header(self):
        """Should handle case-insensitive Retry-After header."""
        error = Mock()
        error.response = Mock()
        error.response.headers = {"retry-after": "60"}

        result = extract_retry_after(error)

        assert result == 60.0

    def test_returns_zero_when_no_headers(self):
        """Should return 0 when no headers present."""
        error = Mock()
        error.response = None

        result = extract_retry_after(error)

        assert result == 0.0

    def test_returns_zero_when_no_retry_after_header(self):
        """Should return 0 when Retry-After header missing."""
        error = Mock()
        error.response = Mock()
        error.response.headers = {"Content-Type": "application/json"}

        result = extract_retry_after(error)

        assert result == 0.0


class TestHandleRateLimitError:
    """Tests for handle_rate_limit_error()."""

    def test_returns_zero_for_non_rate_limit_error(self):
        """Should return 0 for non-429 errors."""
        error = Mock()
        error.status_code = 500

        result = handle_rate_limit_error(error)

        assert result == 0.0

    def test_uses_retry_after_header_when_present(self):
        """Should use Retry-After header value when present."""
        error = Mock()
        error.status_code = 429
        error.response = Mock()
        error.response.headers = {"Retry-After": "90"}

        result = handle_rate_limit_error(error)

        assert result == 90.0

    def test_uses_default_backoff_when_no_header(self):
        """Should use default backoff when no Retry-After header."""
        error = Mock()
        error.status_code = 429
        error.response = Mock()
        error.response.headers = {}

        result = handle_rate_limit_error(error, default_backoff=15.0)

        assert result == 15.0

    def test_caps_default_backoff_at_max(self):
        """Should cap default backoff at MAX_RETRY_AFTER_SECONDS."""
        error = Mock()
        error.status_code = 429
        error.response = Mock()
        error.response.headers = {}

        result = handle_rate_limit_error(error, default_backoff=9999.0)

        assert result == MAX_RETRY_AFTER_SECONDS


class TestWaitForRateLimit:
    """Tests for wait_for_rate_limit()."""

    def test_waits_for_rate_limit_error(self):
        """Should wait for rate limit and return True."""
        error = Mock()
        error.status_code = 429
        error.response = Mock()
        error.response.headers = {"Retry-After": "0.1"}  # Short wait for test

        start_time = time.time()
        result = wait_for_rate_limit(error)
        elapsed = time.time() - start_time

        assert result is True
        assert elapsed >= 0.1  # Should have waited at least 0.1s

    def test_does_not_wait_for_non_rate_limit_error(self):
        """Should not wait for non-rate-limit errors."""
        error = Mock()
        error.status_code = 500

        start_time = time.time()
        result = wait_for_rate_limit(error)
        elapsed = time.time() - start_time

        assert result is False
        assert elapsed < 0.05  # Should not have waited

    def test_uses_default_backoff_when_needed(self):
        """Should use default backoff when no Retry-After header."""
        error = Mock()
        error.status_code = 429
        error.response = Mock()
        error.response.headers = {}

        start_time = time.time()
        result = wait_for_rate_limit(error, default_backoff=0.1)
        elapsed = time.time() - start_time

        assert result is True
        assert elapsed >= 0.1  # Should have waited at least 0.1s


class TestIntegrationScenarios:
    """Integration tests for real-world scenarios."""

    def test_azure_sdk_error_with_retry_after_seconds(self):
        """Should handle Azure SDK error with Retry-After in seconds."""
        # Simulate Azure HttpResponseError
        error = Mock()
        error.status_code = 429
        error.response = Mock()
        error.response.headers = {"Retry-After": "30"}

        assert is_rate_limit_error(error) is True
        wait_time = extract_retry_after(error)
        assert wait_time == 30.0

    def test_azure_sdk_error_with_retry_after_http_date(self):
        """Should handle Azure SDK error with Retry-After as HTTP date."""
        # Create future time
        future_time = datetime.now(UTC) + timedelta(seconds=45)
        http_date = format_datetime(future_time)

        error = Mock()
        error.status_code = 429
        error.response = Mock()
        error.response.headers = {"Retry-After": http_date}

        wait_time = extract_retry_after(error)
        assert 43 <= wait_time <= 47  # Allow small tolerance

    def test_azure_sdk_error_without_retry_after(self):
        """Should handle Azure SDK error without Retry-After header."""
        error = Mock()
        error.status_code = 429
        error.response = Mock()
        error.response.headers = {}

        wait_time = handle_rate_limit_error(error, default_backoff=20.0)
        assert wait_time == 20.0

    def test_consecutive_rate_limits_with_backoff(self):
        """Should handle consecutive rate limits with increasing backoff."""
        error = Mock()
        error.status_code = 429
        error.response = Mock()
        error.response.headers = {}

        # Simulate consecutive rate limits with exponential backoff
        wait_times = []
        backoff = 5.0

        for _ in range(3):
            wait_time = handle_rate_limit_error(error, default_backoff=backoff)
            wait_times.append(wait_time)
            backoff *= 2  # Exponential backoff

        assert wait_times == [5.0, 10.0, 20.0]
