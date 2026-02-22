"""Bastion tunnel creation and retry logic.

Extracted from vm_connector.py (Issue #597) to reduce module size.
Handles Bastion detection, tunnel creation with exponential backoff retry,
and SSHFS mount offers.

Public API:
    get_config_int: Get integer config from environment with safe fallback
    create_tunnel_with_retry: Create Bastion tunnel with retry logic
    check_bastion_routing: Check if Bastion routing should be used for VM
    create_bastion_tunnel: Create Bastion tunnel for VM connection
"""

import logging
import os
import random
import time

import click

from azlin.config_manager import ConfigManager
from azlin.modules.bastion_config import BastionConfig
from azlin.modules.bastion_detector import BastionDetector, BastionInfo
from azlin.modules.bastion_manager import BastionManager, BastionManagerError, BastionTunnel
from azlin.modules.connection_sanitizer import sanitize_for_logging
from azlin.vm_manager import VMManager

logger = logging.getLogger(__name__)


def get_config_int(env_var: str, default: int) -> int:
    """Get integer config from environment with safe fallback."""
    try:
        return int(os.getenv(env_var, default))
    except (ValueError, TypeError):
        return default


def create_tunnel_with_retry(
    bastion_manager: BastionManager,
    bastion_name: str,
    bastion_resource_group: str,
    vm_resource_id: str,
    local_port: int,
    max_attempts: int = 3,
):
    """Create Bastion tunnel with retry logic.

    Args:
        bastion_manager: BastionManager instance
        bastion_name: Bastion host name
        bastion_resource_group: Bastion resource group
        vm_resource_id: Full Azure VM resource ID
        local_port: Local port to bind tunnel to
        max_attempts: Maximum retry attempts (default: 3)

    Returns:
        BastionTunnel ready for use

    Raises:
        BastionManagerError: If tunnel creation fails after all retries
    """
    last_error: Exception | None = None
    initial_delay = 1.0

    for attempt in range(1, max_attempts + 1):
        try:
            logger.debug(f"Attempting tunnel creation (attempt {attempt}/{max_attempts})")
            tunnel = bastion_manager.create_tunnel(
                bastion_name=bastion_name,
                resource_group=bastion_resource_group,
                target_vm_id=vm_resource_id,
                local_port=local_port,
                remote_port=22,
            )
            if attempt > 1:
                logger.info(f"Tunnel created successfully (attempt {attempt}/{max_attempts})")
            return tunnel

        except (BastionManagerError, TimeoutError, ConnectionError) as e:
            last_error = e
            if attempt < max_attempts:
                delay = initial_delay * (2 ** (attempt - 1))
                delay *= 1 + random.uniform(-0.2, 0.2)  # noqa: S311
                logger.warning(
                    f"Tunnel creation failed (attempt {attempt}/{max_attempts}), "
                    f"retrying in {delay:.1f}s: {e}"
                )
                time.sleep(delay)
            else:
                logger.error(f"Tunnel creation failed after {max_attempts} attempts: {e}")

    raise BastionManagerError(
        f"Failed to create Bastion tunnel after {max_attempts} attempts"
    ) from last_error


def check_bastion_routing(
    vm_name: str,
    resource_group: str,
    force_bastion: bool,
    vm_location: str | None = None,
    skip_prompts: bool = False,
) -> BastionInfo | None:
    """Check if Bastion routing should be used for VM.

    Checks configuration and auto-detects Bastion hosts.

    Args:
        vm_name: VM name
        resource_group: Resource group
        force_bastion: Force use of Bastion
        vm_location: VM region for Bastion region filtering (optional)
        skip_prompts: Skip confirmation prompts (default: False)

    Returns:
        BastionInfo with bastion name, resource_group, and location if should use Bastion, None otherwise
    """
    # If forcing Bastion, skip checks
    if force_bastion:
        return None  # Caller will provide bastion_name

    # Load Bastion config
    try:
        config_path = ConfigManager.DEFAULT_CONFIG_DIR / "bastion_config.toml"
        bastion_config = BastionConfig.load(config_path)

        # Check if auto-detection is disabled
        if not bastion_config.auto_detect:
            logger.debug("Bastion auto-detection disabled in config")
            return None

        # Check for explicit mapping
        mapping = bastion_config.get_mapping(vm_name)
        if mapping:
            logger.info(f"Using configured Bastion mapping for {sanitize_for_logging(vm_name)}")
            return BastionInfo(
                name=mapping.bastion_name,
                resource_group=mapping.bastion_resource_group,
                location=None,
            )

    except Exception as e:
        logger.debug(f"Could not load Bastion config: {e}")

    # Auto-detect Bastion
    try:
        bastion_info: BastionInfo | None = BastionDetector.detect_bastion_for_vm(
            vm_name, resource_group, vm_location
        )

        if bastion_info:
            # Prompt user or auto-accept if skip_prompts (default changed to True for security by default)
            if skip_prompts:
                logger.info("Skipping prompts, using Bastion (default)")
                return bastion_info

            try:
                if click.confirm(
                    f"Found Bastion host '{bastion_info['name']}'. Use it for connection?",
                    default=True,
                ):
                    return bastion_info
                logger.info("User declined Bastion connection, using direct connection")
            except click.exceptions.Abort:
                # Non-interactive mode - use default (True)
                logger.info("Non-interactive mode, using Bastion (default)")
                return bastion_info

            logger.info("User declined Bastion connection, using direct connection")

    except Exception as e:
        logger.debug(f"Bastion detection failed: {e}")

    return None


def create_bastion_tunnel(
    vm_name: str,
    resource_group: str,
    bastion_name: str,
    bastion_resource_group: str,
) -> tuple[BastionManager, BastionTunnel]:
    """Create Bastion tunnel for VM connection.

    Args:
        vm_name: VM name
        resource_group: VM resource group
        bastion_name: Bastion host name
        bastion_resource_group: Bastion resource group

    Returns:
        Tuple of (BastionManager, BastionTunnel)

    Raises:
        VMConnectorError: If tunnel creation fails
    """
    from azlin.vm_connector import VMConnectorError

    try:
        # Get VM resource ID
        vm_resource_id = VMManager.get_vm_resource_id(vm_name, resource_group)
        if not vm_resource_id:
            raise VMConnectorError(
                f"Could not determine resource ID for VM: {vm_name}. "
                f"Ensure Azure CLI is authenticated."
            )

        logger.debug(f"Creating tunnel for VM {vm_name}")
        logger.debug(f"Resource ID: {vm_resource_id}")
        logger.debug(f"Bastion: {bastion_name} in {bastion_resource_group}")

        # Create bastion manager
        bastion_manager = BastionManager()

        # Find available port
        local_port = bastion_manager.get_available_port()

        # Get retry attempts from environment
        retry_attempts = get_config_int("AZLIN_BASTION_RETRY_ATTEMPTS", 3)

        # Create tunnel with retry logic (Issue #588)
        tunnel = create_tunnel_with_retry(
            bastion_manager=bastion_manager,
            bastion_name=bastion_name,
            bastion_resource_group=bastion_resource_group,
            vm_resource_id=vm_resource_id,
            local_port=local_port,
            max_attempts=retry_attempts,
        )

        return (bastion_manager, tunnel)

    except BastionManagerError as e:
        raise VMConnectorError(f"Failed to create Bastion tunnel: {e}") from e
    except VMConnectorError:
        raise
    except Exception as e:
        raise VMConnectorError(f"Unexpected error creating Bastion tunnel: {e}") from e


__all__ = [
    "check_bastion_routing",
    "create_bastion_tunnel",
    "create_tunnel_with_retry",
    "get_config_int",
]
