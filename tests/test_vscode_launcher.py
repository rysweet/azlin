"""Tests for VS Code Remote Development Integration."""

import json
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from azlin.modules.vscode_config import VSCodeConfig
from azlin.modules.vscode_launcher import (
    VSCodeLauncher,
    VSCodeLauncherError,
    VSCodeNotFoundError,
)


class TestVSCodeConfig:
    """Tests for VSCodeConfig class."""

    def test_generate_ssh_config_entry(self, tmp_path: Path):
        """Test SSH config entry generation."""
        config = VSCodeConfig(
            vm_name="test-vm",
            host="10.0.0.5",
            user="azureuser",
            key_path=Path("~/.ssh/test_key"),
        )

        entry = config.generate_ssh_config_entry()

        assert "Host azlin-test-vm" in entry
        assert "HostName 10.0.0.5" in entry
        assert "User azureuser" in entry
        # Path is expanded, so check for the expanded form
        assert "IdentityFile" in entry
        assert ".ssh/test_key" in entry
        assert "StrictHostKeyChecking no" in entry

    def test_load_extensions_default(self, tmp_path: Path):
        """Test loading extensions with defaults when config file doesn't exist."""
        config = VSCodeConfig(
            vm_name="test-vm",
            host="10.0.0.5",
            user="azureuser",
            key_path=Path("~/.ssh/test_key"),
            config_dir=tmp_path / "nonexistent",
        )

        extensions = config.load_extensions()

        # Should return default extensions
        assert len(extensions) > 0
        assert "ms-python.python" in extensions

    def test_load_extensions_from_file(self, tmp_path: Path):
        """Test loading extensions from config file."""
        config_dir = tmp_path / ".azlin" / "vscode"
        config_dir.mkdir(parents=True)
        ext_file = config_dir / "extensions.json"
        ext_file.write_text(json.dumps({"extensions": ["custom.extension", "another.extension"]}))

        config = VSCodeConfig(
            vm_name="test-vm",
            host="10.0.0.5",
            user="azureuser",
            key_path=Path("~/.ssh/test_key"),
            config_dir=config_dir,
        )

        extensions = config.load_extensions()

        assert extensions == ["custom.extension", "another.extension"]

    def test_load_extensions_invalid_json(self, tmp_path: Path):
        """Test handling of invalid JSON in extensions file."""
        config_dir = tmp_path / ".azlin" / "vscode"
        config_dir.mkdir(parents=True)
        ext_file = config_dir / "extensions.json"
        ext_file.write_text("invalid json")

        config = VSCodeConfig(
            vm_name="test-vm",
            host="10.0.0.5",
            user="azureuser",
            key_path=Path("~/.ssh/test_key"),
            config_dir=config_dir,
        )

        # Should fall back to defaults on invalid JSON
        extensions = config.load_extensions()
        assert len(extensions) > 0

    def test_load_port_forwards_default(self, tmp_path: Path):
        """Test loading port forwards with defaults."""
        config = VSCodeConfig(
            vm_name="test-vm",
            host="10.0.0.5",
            user="azureuser",
            key_path=Path("~/.ssh/test_key"),
            config_dir=tmp_path / "nonexistent",
        )

        ports = config.load_port_forwards()

        # Should return default common ports
        assert len(ports) > 0
        assert {"local": 3000, "remote": 3000} in ports

    def test_load_port_forwards_from_file(self, tmp_path: Path):
        """Test loading port forwards from config file."""
        config_dir = tmp_path / ".azlin" / "vscode"
        config_dir.mkdir(parents=True)
        ports_file = config_dir / "ports.json"
        ports_file.write_text(
            json.dumps(
                {"forwards": [{"local": 9000, "remote": 9000}, {"local": 5432, "remote": 5432}]}
            )
        )

        config = VSCodeConfig(
            vm_name="test-vm",
            host="10.0.0.5",
            user="azureuser",
            key_path=Path("~/.ssh/test_key"),
            config_dir=config_dir,
        )

        ports = config.load_port_forwards()

        assert ports == [{"local": 9000, "remote": 9000}, {"local": 5432, "remote": 5432}]

    def test_validate_extension_id_valid(self):
        """Test validation of valid extension IDs."""
        config = VSCodeConfig(
            vm_name="test-vm",
            host="10.0.0.5",
            user="azureuser",
            key_path=Path("~/.ssh/test_key"),
        )

        assert config._validate_extension_id("ms-python.python")
        assert config._validate_extension_id("github.copilot")
        assert config._validate_extension_id("publisher.simple-extension")

    def test_validate_extension_id_invalid(self):
        """Test validation of invalid extension IDs."""
        config = VSCodeConfig(
            vm_name="test-vm",
            host="10.0.0.5",
            user="azureuser",
            key_path=Path("~/.ssh/test_key"),
        )

        assert not config._validate_extension_id("invalid space")
        assert not config._validate_extension_id("../../../etc/passwd")
        assert not config._validate_extension_id("extension;rm -rf")


class TestVSCodeLauncher:
    """Tests for VSCodeLauncher class."""

    @patch("azlin.modules.vscode_launcher.shutil.which")
    def test_check_vscode_installed_not_found(self, mock_which: MagicMock):
        """Test VS Code CLI detection when not installed."""
        mock_which.return_value = None

        with pytest.raises(VSCodeNotFoundError, match="VS Code CLI not found"):
            VSCodeLauncher.check_vscode_installed()

    @patch("azlin.modules.vscode_launcher.shutil.which")
    def test_check_vscode_installed_found(self, mock_which: MagicMock):
        """Test VS Code CLI detection when installed."""
        mock_which.return_value = "/usr/local/bin/code"

        cli_path = VSCodeLauncher.check_vscode_installed()

        assert cli_path == "/usr/local/bin/code"

    @patch("azlin.modules.vscode_launcher.subprocess.run")
    @patch("azlin.modules.vscode_launcher.shutil.which")
    def test_install_extensions_success(self, mock_which: MagicMock, mock_run: MagicMock):
        """Test successful extension installation."""
        mock_which.return_value = "/usr/local/bin/code"
        mock_run.return_value = Mock(returncode=0)

        extensions = ["ms-python.python", "github.copilot"]
        VSCodeLauncher.install_extensions("azlin-test-vm", extensions)

        # Should call code CLI for each extension
        assert mock_run.call_count == 2

    @patch("azlin.modules.vscode_launcher.subprocess.run")
    @patch("azlin.modules.vscode_launcher.shutil.which")
    def test_install_extensions_failure(self, mock_which: MagicMock, mock_run: MagicMock):
        """Test extension installation failure handling - logs warning but continues."""
        mock_which.return_value = "/usr/local/bin/code"
        mock_run.return_value = Mock(returncode=1, stderr="Extension not found")

        extensions = ["invalid.extension"]

        # Should not raise - logs warning and continues
        VSCodeLauncher.install_extensions("azlin-test-vm", extensions)

    @patch("azlin.modules.vscode_launcher.subprocess.run")
    @patch("azlin.modules.vscode_launcher.shutil.which")
    @patch("azlin.modules.vscode_launcher.Path")
    def test_write_ssh_config_new_entry(
        self, mock_path: MagicMock, mock_which: MagicMock, mock_run: MagicMock
    ):
        """Test writing new SSH config entry."""
        mock_which.return_value = "/usr/local/bin/code"
        mock_ssh_config = MagicMock()
        mock_path.home.return_value = Path("/home/user")
        mock_ssh_config.exists.return_value = True
        mock_ssh_config.read_text.return_value = "# Existing config"

        config = VSCodeConfig(
            vm_name="test-vm",
            host="10.0.0.5",
            user="azureuser",
            key_path=Path("~/.ssh/test_key"),
        )

        # Test that config entry is generated
        entry = config.generate_ssh_config_entry()
        assert "Host azlin-test-vm" in entry

    @patch("azlin.modules.vscode_launcher.subprocess.run")
    @patch("azlin.modules.vscode_launcher.shutil.which")
    def test_launch_vscode_success(self, mock_which: MagicMock, mock_run: MagicMock):
        """Test successful VS Code launch."""
        mock_which.return_value = "/usr/local/bin/code"
        mock_run.return_value = Mock(returncode=0)

        VSCodeLauncher.launch_vscode("azlin-test-vm", "azureuser")

        # Should call code with --folder-uri and vscode-remote URI
        assert mock_run.called
        call_args = mock_run.call_args[0][0]
        assert "code" in call_args[0]
        assert "--folder-uri" in call_args
        assert any("vscode-remote://ssh-remote+" in arg for arg in call_args)

    @patch("azlin.modules.vscode_launcher.subprocess.run")
    @patch("azlin.modules.vscode_launcher.shutil.which")
    def test_launch_vscode_failure(self, mock_which: MagicMock, mock_run: MagicMock):
        """Test VS Code launch failure handling."""
        mock_which.return_value = "/usr/local/bin/code"
        mock_run.return_value = Mock(returncode=1, stderr="Failed to connect")

        with pytest.raises(VSCodeLauncherError, match="Failed to launch VS Code"):
            VSCodeLauncher.launch_vscode("azlin-test-vm", "azureuser")
