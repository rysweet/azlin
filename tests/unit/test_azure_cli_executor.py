"""Tests for azure_cli_executor module.

Tests the run_az_command helper that wraps subprocess.run with retry logic
for Azure CLI calls. Proportional testing: ~100 LOC for ~50 LOC implementation.
"""

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from azlin.azure_cli_executor import run_az_command


class TestRunAzCommand:
    """Test run_az_command helper function."""

    @patch("azlin.azure_cli_executor.subprocess.run")
    def test_success_returns_completed_process(self, mock_run: MagicMock) -> None:
        """Successful az command returns CompletedProcess."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["az", "vm", "list"], returncode=0, stdout='["vm1"]', stderr=""
        )

        result = run_az_command(["az", "vm", "list"])

        assert result.returncode == 0
        assert result.stdout == '["vm1"]'
        mock_run.assert_called_once()

    @patch("azlin.azure_cli_executor.subprocess.run")
    def test_passes_default_kwargs(self, mock_run: MagicMock) -> None:
        """Verifies default capture_output, text, check, timeout are passed."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["az", "account", "show"], returncode=0, stdout="{}", stderr=""
        )

        run_az_command(["az", "account", "show"])

        _, kwargs = mock_run.call_args
        assert kwargs["capture_output"] is True
        assert kwargs["text"] is True
        assert kwargs["check"] is True
        assert kwargs["timeout"] == 30

    @patch("azlin.azure_cli_executor.subprocess.run")
    def test_custom_timeout(self, mock_run: MagicMock) -> None:
        """Custom timeout is forwarded to subprocess.run."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["az", "vm", "create"], returncode=0, stdout="{}", stderr=""
        )

        run_az_command(["az", "vm", "create"], timeout=300)

        _, kwargs = mock_run.call_args
        assert kwargs["timeout"] == 300

    @patch("azlin.azure_cli_executor.subprocess.run")
    def test_retries_on_called_process_error(self, mock_run: MagicMock) -> None:
        """Retries on CalledProcessError (transient Azure failure)."""
        mock_run.side_effect = [
            subprocess.CalledProcessError(1, "az", stderr="ServiceUnavailable"),
            subprocess.CompletedProcess(
                args=["az", "vm", "list"], returncode=0, stdout="[]", stderr=""
            ),
        ]

        result = run_az_command(["az", "vm", "list"], max_attempts=3)

        assert result.returncode == 0
        assert mock_run.call_count == 2

    @patch("azlin.azure_cli_executor.subprocess.run")
    def test_raises_after_max_attempts(self, mock_run: MagicMock) -> None:
        """Raises CalledProcessError after exhausting retry attempts."""
        mock_run.side_effect = subprocess.CalledProcessError(1, "az", stderr="InternalError")

        with pytest.raises(subprocess.CalledProcessError):
            run_az_command(["az", "vm", "list"], max_attempts=2)

        assert mock_run.call_count == 2

    @patch("azlin.azure_cli_executor.subprocess.run")
    def test_retries_on_timeout(self, mock_run: MagicMock) -> None:
        """Retries on TimeoutExpired."""
        mock_run.side_effect = [
            subprocess.TimeoutExpired("az", 30),
            subprocess.CompletedProcess(
                args=["az", "vm", "list"], returncode=0, stdout="[]", stderr=""
            ),
        ]

        result = run_az_command(["az", "vm", "list"], max_attempts=3)

        assert result.returncode == 0
        assert mock_run.call_count == 2

    @patch("azlin.azure_cli_executor.subprocess.run")
    def test_check_false_no_retry_on_nonzero(self, mock_run: MagicMock) -> None:
        """When check=False, non-zero return code does not raise or retry."""
        mock_run.return_value = subprocess.CompletedProcess(
            args=["az", "vm", "show"], returncode=1, stdout="", stderr="NotFound"
        )

        result = run_az_command(["az", "vm", "show"], check=False)

        assert result.returncode == 1
        assert mock_run.call_count == 1
