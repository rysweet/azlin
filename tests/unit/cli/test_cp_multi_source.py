"""Unit tests for multi-source cp command (Issue #323).

Tests for multiple source file support in cp command:
- Single source (backward compatibility)
- Multiple local sources to remote
- Multiple remote sources to local
- Validation: all sources from same location
- Error handling: mixed local/remote sources
- Progress indicators for multiple files
"""

from pathlib import Path
from unittest.mock import Mock, patch

from click.testing import CliRunner

from azlin.cli import main
from azlin.modules.file_transfer.file_transfer import TransferResult
from azlin.modules.file_transfer.session_manager import VMSession


class TestCpMultiSourceSyntax:
    """Test cp command syntax with multiple sources."""

    def test_cp_single_source_backward_compatible(self):
        """Test single source still works (backward compatibility)."""
        runner = CliRunner()
        with patch(
            "azlin.commands.connectivity.ConfigManager.get_resource_group", return_value="test-rg"
        ):
            with patch("azlin.commands.connectivity.SSHKeyManager.ensure_key_exists"):
                with patch(
                    "azlin.commands.connectivity.SessionManager.get_vm_session"
                ) as mock_session:
                    with patch(
                        "azlin.commands.connectivity.FileTransfer.transfer"
                    ) as mock_transfer:
                        # Setup mocks
                        mock_vm_session = Mock(spec=VMSession)
                        mock_vm_session.name = "test-vm"
                        mock_vm_session.user = "azureuser"
                        mock_vm_session.ssh_host = "10.0.0.1"
                        mock_vm_session.ssh_port = 22
                        mock_session.return_value = (mock_vm_session, None)

                        mock_transfer.return_value = TransferResult(
                            success=True,
                            files_transferred=1,
                            bytes_transferred=1024,
                            duration_seconds=0.5,
                            errors=[],
                        )

                        # Act
                        result = runner.invoke(
                            main, ["cp", "test.txt", "test-vm:~/"], catch_exceptions=False
                        )

                        # Assert
                        assert result.exit_code == 0
                        assert "Success!" in result.output
                        mock_transfer.assert_called_once()

    def test_cp_multiple_sources_accepted(self):
        """Test multiple sources are accepted."""
        runner = CliRunner()
        with patch(
            "azlin.commands.connectivity.ConfigManager.get_resource_group", return_value="test-rg"
        ):
            with patch("azlin.commands.connectivity.SSHKeyManager.ensure_key_exists"):
                with patch(
                    "azlin.commands.connectivity.SessionManager.get_vm_session"
                ) as mock_session:
                    with patch(
                        "azlin.commands.connectivity.FileTransfer.transfer"
                    ) as mock_transfer:
                        # Setup mocks
                        mock_vm_session = Mock(spec=VMSession)
                        mock_vm_session.name = "test-vm"
                        mock_vm_session.user = "azureuser"
                        mock_vm_session.ssh_host = "10.0.0.1"
                        mock_vm_session.ssh_port = 22
                        mock_session.return_value = (mock_vm_session, None)

                        mock_transfer.return_value = TransferResult(
                            success=True,
                            files_transferred=1,
                            bytes_transferred=1024,
                            duration_seconds=0.5,
                            errors=[],
                        )

                        # Act
                        result = runner.invoke(
                            main,
                            ["cp", "file1.txt", "file2.txt", "file3.py", "test-vm:~/"],
                            catch_exceptions=False,
                        )

                        # Assert
                        if result.exit_code != 0:
                            print(f"Exit code: {result.exit_code}")
                            print(f"Output: {result.output}")
                            print(f"Exception: {result.exception}")
                        assert result.exit_code == 0
                        assert "Success!" in result.output
                        assert mock_transfer.call_count == 3

    def test_cp_no_source_fails(self):
        """Test cp with no sources fails with error."""
        runner = CliRunner()
        result = runner.invoke(main, ["cp"], catch_exceptions=False)

        # Should show missing argument error
        assert result.exit_code != 0
        assert "Missing argument" in result.output or "Error" in result.output

    def test_cp_only_destination_fails(self):
        """Test cp with only destination fails."""
        runner = CliRunner()
        result = runner.invoke(main, ["cp", "vm:~/"], catch_exceptions=False)

        # Should fail - need at least one source
        assert result.exit_code != 0


class TestCpMultiSourceTransfer:
    """Test multi-source file transfer logic."""

    def test_multiple_local_files_to_remote(self, tmp_path):
        """Test transferring multiple local files to remote VM."""
        # Arrange
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"
        file3 = tmp_path / "file3.py"
        file1.write_text("content1")
        file2.write_text("content2")
        file3.write_text("content3")

        runner = CliRunner()
        with patch(
            "azlin.commands.connectivity.ConfigManager.get_resource_group", return_value="test-rg"
        ):
            with patch("azlin.commands.connectivity.SSHKeyManager.ensure_key_exists"):
                with patch(
                    "azlin.commands.connectivity.SessionManager.get_vm_session"
                ) as mock_session:
                    with patch(
                        "azlin.commands.connectivity.FileTransfer.transfer"
                    ) as mock_transfer:
                        with patch(
                            "azlin.cli.PathParser.parse_and_validate",
                            side_effect=lambda p, **kwargs: Path(p),
                        ):
                            # Setup mocks
                            mock_vm_session = Mock(spec=VMSession)
                            mock_vm_session.name = "test-vm"
                            mock_vm_session.user = "azureuser"
                            mock_vm_session.ssh_host = "10.0.0.1"
                            mock_vm_session.ssh_port = 22
                            mock_session.return_value = (mock_vm_session, None)

                            mock_transfer.return_value = TransferResult(
                                success=True,
                                files_transferred=1,
                                bytes_transferred=1024,
                                duration_seconds=0.5,
                                errors=[],
                            )

                            # Act
                            result = runner.invoke(
                                main,
                                [
                                    "cp",
                                    str(file1),
                                    str(file2),
                                    str(file3),
                                    "test-vm:~/",
                                ],
                                catch_exceptions=False,
                            )

                            # Assert
                            assert result.exit_code == 0
                            assert mock_transfer.call_count == 3
                            assert "Success!" in result.output

    def test_multiple_sources_shows_progress(self, tmp_path):
        """Test multiple sources display progress indicators."""
        # Arrange
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"
        file1.write_text("content1")
        file2.write_text("content2")

        runner = CliRunner()
        with patch(
            "azlin.commands.connectivity.ConfigManager.get_resource_group", return_value="test-rg"
        ):
            with patch("azlin.commands.connectivity.SSHKeyManager.ensure_key_exists"):
                with patch(
                    "azlin.commands.connectivity.SessionManager.get_vm_session"
                ) as mock_session:
                    with patch(
                        "azlin.commands.connectivity.FileTransfer.transfer"
                    ) as mock_transfer:
                        with patch(
                            "azlin.cli.PathParser.parse_and_validate",
                            side_effect=lambda p, **kwargs: Path(p),
                        ):
                            # Setup mocks
                            mock_vm_session = Mock(spec=VMSession)
                            mock_vm_session.name = "test-vm"
                            mock_vm_session.user = "azureuser"
                            mock_vm_session.ssh_host = "10.0.0.1"
                            mock_vm_session.ssh_port = 22
                            mock_session.return_value = (mock_vm_session, None)

                            mock_transfer.return_value = TransferResult(
                                success=True,
                                files_transferred=1,
                                bytes_transferred=1024,
                                duration_seconds=0.5,
                                errors=[],
                            )

                            # Act
                            result = runner.invoke(
                                main,
                                ["cp", str(file1), str(file2), "test-vm:~/"],
                                catch_exceptions=False,
                            )

                            # Assert
                            assert result.exit_code == 0
                            # Should show progress for multiple files
                            assert "[1/2]" in result.output
                            assert "[2/2]" in result.output
                            assert "✓" in result.output or "KB" in result.output

    def test_dry_run_shows_all_sources(self, tmp_path):
        """Test --dry-run shows all source files in plan."""
        # Arrange
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"
        file1.write_text("content1")
        file2.write_text("content2")

        runner = CliRunner()
        with patch(
            "azlin.commands.connectivity.ConfigManager.get_resource_group", return_value="test-rg"
        ):
            with patch("azlin.commands.connectivity.SSHKeyManager.ensure_key_exists"):
                with patch(
                    "azlin.commands.connectivity.SessionManager.get_vm_session"
                ) as mock_session:
                    with patch(
                        "azlin.cli.PathParser.parse_and_validate",
                        side_effect=lambda p, **kwargs: Path(p),
                    ):
                        # Setup mocks
                        mock_vm_session = Mock(spec=VMSession)
                        mock_vm_session.name = "test-vm"
                        mock_vm_session.user = "azureuser"
                        mock_vm_session.ssh_host = "10.0.0.1"
                        mock_vm_session.ssh_port = 22
                        mock_session.return_value = (mock_vm_session, None)

                        # Act
                        result = runner.invoke(
                            main,
                            ["cp", "--dry-run", str(file1), str(file2), "test-vm:~/"],
                            catch_exceptions=False,
                        )

                        # Assert
                        assert result.exit_code == 0
                        assert "Transfer Plan:" in result.output
                        assert "2 files" in result.output
                        assert "Dry run" in result.output


class TestCpMultiSourceValidation:
    """Test validation logic for multi-source transfers."""

    def test_mixed_local_remote_sources_rejected(self):
        """Test error when mixing local and remote sources."""
        runner = CliRunner()
        with patch(
            "azlin.commands.connectivity.ConfigManager.get_resource_group", return_value="test-rg"
        ):
            with patch("azlin.commands.connectivity.SSHKeyManager.ensure_key_exists"):
                with patch(
                    "azlin.commands.connectivity.SessionManager.get_vm_session"
                ) as mock_session:
                    with patch(
                        "azlin.cli.PathParser.parse_and_validate",
                        side_effect=lambda p, **kwargs: Path(p),
                    ):
                        # Setup mocks
                        mock_vm_session = Mock(spec=VMSession)
                        mock_vm_session.name = "test-vm"
                        mock_vm_session.user = "azureuser"
                        mock_vm_session.ssh_host = "10.0.0.1"
                        mock_vm_session.ssh_port = 22
                        mock_session.return_value = (mock_vm_session, None)

                        # Act - mixing local and remote sources
                        result = runner.invoke(
                            main,
                            ["cp", "local.txt", "vm:~/remote.txt", "dest-vm:~/"],
                            catch_exceptions=False,
                        )

                        # Assert
                        assert result.exit_code != 0
                        assert (
                            "same location" in result.output.lower()
                            or "all local" in result.output.lower()
                            or "all from the same" in result.output.lower()
                        )

    def test_multiple_remote_sources_different_vms_rejected(self):
        """Test error when sources are from different VMs."""
        runner = CliRunner()
        with patch(
            "azlin.commands.connectivity.ConfigManager.get_resource_group", return_value="test-rg"
        ):
            with patch("azlin.commands.connectivity.SSHKeyManager.ensure_key_exists"):
                with patch(
                    "azlin.commands.connectivity.SessionManager.get_vm_session"
                ) as mock_session:
                    with patch(
                        "azlin.cli.PathParser.parse_and_validate",
                        side_effect=lambda p, **kwargs: Path(p),
                    ):
                        # Setup mocks - return different VMs
                        def get_session(name, *args, **kwargs):
                            session = Mock(spec=VMSession)
                            session.name = name
                            session.user = "azureuser"
                            session.ssh_host = "10.0.0.1"
                            session.ssh_port = 22
                            return (session, None)

                        mock_session.side_effect = get_session

                        # Act - sources from different VMs
                        result = runner.invoke(
                            main,
                            ["cp", "vm1:~/file1.txt", "vm2:~/file2.txt", "local-dest/"],
                            catch_exceptions=False,
                        )

                        # Assert
                        assert result.exit_code != 0
                        assert (
                            "same VM" in result.output or "same location" in result.output.lower()
                        )


class TestCpMultiSourceErrorHandling:
    """Test error handling for multi-source transfers."""

    def test_partial_failure_reports_errors(self, tmp_path):
        """Test partial failures are properly reported."""
        # Arrange
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"
        file1.write_text("content1")
        file2.write_text("content2")

        runner = CliRunner()
        with patch(
            "azlin.commands.connectivity.ConfigManager.get_resource_group", return_value="test-rg"
        ):
            with patch("azlin.commands.connectivity.SSHKeyManager.ensure_key_exists"):
                with patch(
                    "azlin.commands.connectivity.SessionManager.get_vm_session"
                ) as mock_session:
                    with patch(
                        "azlin.commands.connectivity.FileTransfer.transfer"
                    ) as mock_transfer:
                        with patch(
                            "azlin.cli.PathParser.parse_and_validate",
                            side_effect=lambda p, **kwargs: Path(p),
                        ):
                            # Setup mocks
                            mock_vm_session = Mock(spec=VMSession)
                            mock_vm_session.name = "test-vm"
                            mock_vm_session.user = "azureuser"
                            mock_vm_session.ssh_host = "10.0.0.1"
                            mock_vm_session.ssh_port = 22
                            mock_session.return_value = (mock_vm_session, None)

                            # First transfer succeeds, second fails
                            mock_transfer.side_effect = [
                                TransferResult(
                                    success=True,
                                    files_transferred=1,
                                    bytes_transferred=1024,
                                    duration_seconds=0.5,
                                    errors=[],
                                ),
                                TransferResult(
                                    success=False,
                                    files_transferred=0,
                                    bytes_transferred=0,
                                    duration_seconds=0.1,
                                    errors=["rsync failed: connection refused"],
                                ),
                            ]

                            # Act
                            result = runner.invoke(
                                main,
                                ["cp", str(file1), str(file2), "test-vm:~/"],
                                catch_exceptions=False,
                            )

                            # Assert
                            assert result.exit_code != 0
                            assert "errors" in result.output.lower()
                            assert "rsync failed" in result.output

    def test_all_sources_must_exist(self):
        """Test error when source file doesn't exist."""
        runner = CliRunner()
        with patch(
            "azlin.commands.connectivity.ConfigManager.get_resource_group", return_value="test-rg"
        ):
            with patch("azlin.commands.connectivity.SSHKeyManager.ensure_key_exists"):
                # Act - non-existent files
                result = runner.invoke(
                    main,
                    ["cp", "nonexistent1.txt", "nonexistent2.txt", "vm:~/"],
                    catch_exceptions=False,
                )

                # Assert
                assert result.exit_code != 0
