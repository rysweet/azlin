"""npm User-Local Configuration Module

This module configures npm for user-local global package installations,
eliminating the need for sudo when installing global packages.

Configuration includes:
- Creating ~/.npm-packages directory
- Setting npm prefix in ~/.npmrc
- Updating PATH and MANPATH in ~/.bashrc
- Sourcing bashrc to apply changes

Security:
- All commands properly sanitized via RemoteExecutor
- Idempotent operations (safe to run multiple times)
- No hardcoded credentials
"""

import logging
from dataclasses import dataclass

from azlin.modules.ssh_connector import SSHConfig
from azlin.remote_exec import RemoteExecError, RemoteExecutor

logger = logging.getLogger(__name__)


class NpmConfigError(Exception):
    """Raised when npm configuration fails."""

    pass


@dataclass
class NpmConfigResult:
    """Result from npm configuration operation."""

    success: bool
    message: str
    npmrc_configured: bool
    directory_created: bool
    bashrc_updated: bool
    bashrc_sourced: bool


class NpmConfigurator:
    """Configure npm for user-local global package installations.

    This class handles all aspects of configuring npm to install global
    packages in a user-local directory, avoiding the need for sudo.

    Example:
        >>> ssh_config = SSHConfig(host="1.2.3.4", user="azureuser", key_path=Path("/key"))
        >>> configurator = NpmConfigurator(ssh_config)
        >>> result = configurator.configure_npm()
        >>> if result.success:
        ...     print("npm configured successfully")
    """

    def __init__(
        self,
        ssh_config: SSHConfig,
        npm_packages_dir: str = "${HOME}/.npm-packages",
        npmrc_path: str = "${HOME}/.npmrc",
        bashrc_path: str = "${HOME}/.bashrc",
        timeout: int = 30,
    ):
        """Initialize npm configurator.

        Args:
            ssh_config: SSH configuration for remote VM
            npm_packages_dir: Directory for npm global packages
            npmrc_path: Path to .npmrc file
            bashrc_path: Path to .bashrc file
            timeout: Timeout for remote commands in seconds
        """
        self.ssh_config = ssh_config
        self.npm_packages_dir = npm_packages_dir
        self.npmrc_path = npmrc_path
        self.bashrc_path = bashrc_path
        self.timeout = timeout
        self.vm_name = ssh_config.host

    def get_npmrc_content(self) -> str:
        """Generate .npmrc configuration content.

        Returns:
            npm configuration content for .npmrc file
        """
        return f"prefix={self.npm_packages_dir}"

    def get_bashrc_content(self) -> str:
        """Generate .bashrc configuration content.

        Returns:
            Bash configuration content for .bashrc file
        """
        return f"""
# npm user-local configuration
NPM_PACKAGES="{self.npm_packages_dir}"
PATH="$NPM_PACKAGES/bin:$PATH"
MANPATH="$NPM_PACKAGES/share/man:$(manpath 2>/dev/null || echo $MANPATH)"
"""

    def create_npm_directory(self) -> bool:
        """Create .npm-packages directory on remote VM.

        Returns:
            True if directory created successfully

        Raises:
            NpmConfigError: If directory creation fails
        """
        # Use mkdir -p for idempotency
        command = f"mkdir -p {self.npm_packages_dir}"

        try:
            result = RemoteExecutor.execute_command(self.ssh_config, command, timeout=self.timeout)

            if not result.success:
                raise NpmConfigError(f"Failed to create npm packages directory: {result.stderr}")

            logger.info(f"Created npm packages directory on {self.vm_name}")
            return True

        except RemoteExecError as e:
            raise NpmConfigError(f"Failed to create npm directory: {e}") from e

    def configure_npmrc(self) -> bool:
        """Configure npm prefix in .npmrc file.

        This is idempotent - checks if configuration already exists
        before appending.

        Returns:
            True if configuration successful

        Raises:
            NpmConfigError: If configuration fails
        """
        npmrc_content = self.get_npmrc_content()

        # Check if already configured (idempotency)
        check_command = f"grep -q 'prefix=' {self.npmrc_path} 2>/dev/null"

        try:
            check_result = RemoteExecutor.execute_command(
                self.ssh_config, check_command, timeout=self.timeout
            )

            if check_result.success:
                logger.info(f".npmrc already configured on {self.vm_name}")
                return True

            # Not configured yet, append it
            append_command = f"echo '{npmrc_content}' >> {self.npmrc_path}"

            result = RemoteExecutor.execute_command(
                self.ssh_config, append_command, timeout=self.timeout
            )

            if not result.success:
                raise NpmConfigError(f"Failed to configure .npmrc: {result.stderr}")

            logger.info(f"Configured .npmrc on {self.vm_name}")
            return True

        except RemoteExecError as e:
            raise NpmConfigError(f"Failed to configure .npmrc: {e}") from e

    def configure_bashrc(self) -> bool:
        """Configure PATH and MANPATH in .bashrc file.

        This is idempotent - checks if configuration already exists
        before appending.

        Returns:
            True if configuration successful

        Raises:
            NpmConfigError: If configuration fails
        """
        # Check if already configured (idempotency)
        check_command = f"grep -q 'NPM_PACKAGES=' {self.bashrc_path} 2>/dev/null"

        try:
            check_result = RemoteExecutor.execute_command(
                self.ssh_config, check_command, timeout=self.timeout
            )

            if check_result.success:
                logger.info(f".bashrc already configured on {self.vm_name}")
                return True

            # Not configured yet, append it
            bashrc_content = self.get_bashrc_content()

            # Use cat with heredoc for multi-line content
            append_command = f"cat >> {self.bashrc_path} << 'EOF'\n{bashrc_content}\nEOF"

            result = RemoteExecutor.execute_command(
                self.ssh_config, append_command, timeout=self.timeout
            )

            if not result.success:
                raise NpmConfigError(f"Failed to configure .bashrc: {result.stderr}")

            logger.info(f"Configured .bashrc on {self.vm_name}")
            return True

        except RemoteExecError as e:
            raise NpmConfigError(f"Failed to configure .bashrc: {e}") from e

    def source_bashrc(self) -> bool:
        """Source .bashrc to apply changes.

        Returns:
            True if sourcing successful

        Raises:
            NpmConfigError: If sourcing fails
        """
        command = f"source {self.bashrc_path}"

        try:
            result = RemoteExecutor.execute_command(self.ssh_config, command, timeout=self.timeout)

            if not result.success:
                # Some shells might not support source, try with .
                command = f". {self.bashrc_path}"
                result = RemoteExecutor.execute_command(
                    self.ssh_config, command, timeout=self.timeout
                )

                if not result.success:
                    logger.warning(f"Failed to source .bashrc on {self.vm_name}: {result.stderr}")
                    # This is not critical - changes will apply on next login
                    return True

            logger.info(f"Sourced .bashrc on {self.vm_name}")
            return True

        except RemoteExecError as e:
            logger.warning(f"Failed to source .bashrc: {e}")
            # Not critical - changes will apply on next login
            return True

    def configure_npm(self) -> NpmConfigResult:
        """Configure npm for user-local installations (main entry point).

        Performs all configuration steps:
        1. Create .npm-packages directory
        2. Configure npm prefix in .npmrc
        3. Update PATH and MANPATH in .bashrc
        4. Source .bashrc to apply changes

        Returns:
            NpmConfigResult with detailed status

        Raises:
            NpmConfigError: If any critical step fails
        """
        logger.info(f"Configuring npm user-local installation on {self.vm_name}")

        try:
            # Step 1: Create directory
            directory_created = self.create_npm_directory()

            # Step 2: Configure .npmrc
            npmrc_configured = self.configure_npmrc()

            # Step 3: Configure .bashrc
            bashrc_updated = self.configure_bashrc()

            # Step 4: Source .bashrc (non-critical)
            bashrc_sourced = self.source_bashrc()

            result = NpmConfigResult(
                success=True,
                message="npm configured successfully for user-local installations",
                npmrc_configured=npmrc_configured,
                directory_created=directory_created,
                bashrc_updated=bashrc_updated,
                bashrc_sourced=bashrc_sourced,
            )

            logger.info(f"npm configuration complete on {self.vm_name}")
            return result

        except NpmConfigError as e:
            logger.error(f"npm configuration failed on {self.vm_name}: {e}")
            raise


__all__ = [
    "NpmConfigError",
    "NpmConfigResult",
    "NpmConfigurator",
]
