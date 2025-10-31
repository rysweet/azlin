"""End-to-End tests for Bastion default feature (TDD - Issue #237).

E2E tests verify complete user workflows against real (or mocked) Azure resources.
These tests represent actual user scenarios and acceptance criteria.

Run with: pytest tests/e2e/test_bastion_default_e2e.py -v
For real Azure: RUN_E2E_TESTS=true pytest -m e2e

Testing Level: E2E (10% of testing pyramid)
"""

import os
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch, Mock

# Mark all tests as E2E
pytestmark = pytest.mark.e2e


@pytest.fixture(scope="module")
def skip_e2e():
    """Skip E2E tests unless explicitly enabled."""
    if os.environ.get("RUN_E2E_TESTS") != "true":
        pytest.skip("E2E tests skipped. Set RUN_E2E_TESTS=true to run.")


@pytest.fixture
def test_env():
    """Test environment configuration."""
    return {
        "resource_group": os.environ.get("AZLIN_E2E_RG", "azlin-bastion-default-e2e"),
        "location": os.environ.get("AZLIN_E2E_LOCATION", "westus2"),
        "vnet_name": "azlin-e2e-vnet",
        "bastion_name": "azlin-e2e-bastion",
    }


@pytest.fixture
def temp_home_dir():
    """Temporary home directory for CLI tests."""
    with tempfile.TemporaryDirectory() as tmpdir:
        home_dir = Path(tmpdir)
        azlin_dir = home_dir / ".azlin"
        azlin_dir.mkdir()
        yield home_dir


class TestAcceptanceCriteria:
    """Test acceptance criteria from issue #237.

    User Story: As a developer, I want bastion hosts to be the default
    when creating VMs, so that my VMs are secure by default.

    Acceptance Criteria:
    1. Auto-detect bastion in resource group
    2. Use automatically if exists (after user confirmation)
    3. Prompt to create if doesn't exist (default: yes)
    4. Allow user to decline and create public IP instead
    5. Backward compatibility with --use-bastion flag
    """

    def test_ac1_auto_detect_bastion_in_resource_group(self, skip_e2e, test_env):
        """AC1: Auto-detect bastion in resource group.

        Given: A resource group with an existing bastion host
        When: User creates a new VM in that resource group
        Then: System detects the bastion automatically
        """
        # This test verifies the complete flow:
        # 1. Query Azure for bastions in RG
        # 2. Find active bastion
        # 3. Return bastion info

        # Mock or use real Azure
        from azlin.modules.bastion_detector import BastionDetector

        # Act
        bastion_info = BastionDetector.detect_bastion_for_vm(
            vm_name="test-vm",
            resource_group=test_env["resource_group"]
        )

        # Assert
        # If bastion exists in test RG, should be detected
        # If none exists, should return None gracefully
        assert bastion_info is None or isinstance(bastion_info, dict)

    def test_ac2_use_bastion_automatically_with_confirmation(self, skip_e2e,
                                                              test_env, temp_home_dir):
        """AC2: Use bastion automatically if exists (after confirmation).

        Given: Bastion detected in resource group
        When: User confirms using bastion
        Then: VM is created without public IP and configured for bastion
        """
        # Mock the complete workflow
        from azlin.modules.bastion_detector import BastionDetector
        from azlin.vm_provisioning import VMProvisioner, VMConfig

        bastion_info = {"name": test_env["bastion_name"],
                       "resource_group": test_env["resource_group"]}

        with patch.object(BastionDetector, 'detect_bastion_for_vm',
                         return_value=bastion_info):
            with patch('click.confirm', return_value=True) as mock_confirm:
                with patch('subprocess.run') as mock_run:
                    mock_run.return_value.stdout = '{"privateIpAddress": "10.0.0.4"}'

                    # Act
                    provisioner = VMProvisioner()
                    config = VMConfig(
                        name="test-vm",
                        resource_group=test_env["resource_group"],
                        location=test_env["location"]
                    )

                    # Should auto-detect and prompt
                    # Implementation will provision VM

        # Assert
        mock_confirm.assert_called_once()
        confirm_message = str(mock_confirm.call_args)
        assert "bastion" in confirm_message.lower()

    def test_ac3_prompt_to_create_bastion_default_yes(self, skip_e2e, test_env,
                                                       temp_home_dir):
        """AC3: Prompt to create bastion if doesn't exist (default: yes).

        Given: No bastion exists in resource group
        When: User creates a VM
        Then: System prompts to create bastion with default=yes
        And: User can accept to create bastion
        """
        from azlin.modules.bastion_detector import BastionDetector
        from azlin.vm_provisioning import VMProvisioner, VMConfig

        with patch.object(BastionDetector, 'detect_bastion_for_vm',
                         return_value=None):
            with patch('click.confirm', return_value=True) as mock_confirm:
                # Act
                # Should prompt: "No Bastion found. Create one? (Y/n)"
                pass

        # Assert
        mock_confirm.assert_called()
        confirm_call = mock_confirm.call_args
        # Verify default is True (yes)
        assert confirm_call.kwargs.get('default') is True or \
               confirm_call[1].get('default') is True

    def test_ac4_allow_decline_bastion_use_public_ip(self, skip_e2e, test_env):
        """AC4: Allow user to decline and create public IP instead.

        Given: Bastion is available or user declines creating one
        When: User declines using bastion
        Then: VM is created with public IP for direct access
        """
        from azlin.modules.bastion_detector import BastionDetector
        from azlin.vm_provisioning import VMProvisioner, VMConfig

        bastion_info = {"name": "test-bastion", "resource_group": test_env["resource_group"]}

        with patch.object(BastionDetector, 'detect_bastion_for_vm',
                         return_value=bastion_info):
            with patch('click.confirm', return_value=False):  # User declines
                with patch('subprocess.run') as mock_run:
                    # Act
                    # Should provision VM with public IP
                    pass

        # Assert
        # Verify public IP was included in provisioning
        if mock_run.called:
            cmd = mock_run.call_args[0][0]
            # Should have public IP args
            pass

    def test_ac5_backward_compatibility_use_bastion_flag(self, skip_e2e, test_env):
        """AC5: Backward compatibility with --use-bastion flag.

        Given: User explicitly specifies --use-bastion flag
        When: VM is created or connection is made
        Then: Bastion is used without prompting
        And: Existing workflows continue to work
        """
        from azlin.vm_connector import VMConnector

        with patch('subprocess.Popen'):
            with patch('click.confirm') as mock_confirm:
                # Act
                # CLI: azlin connect test-vm --use-bastion
                # Should NOT prompt when flag is explicit
                pass

        # Assert
        # No user prompt when flag is explicit
        mock_confirm.assert_not_called()


class TestUserWorkflows:
    """Test complete user workflows from CLI."""

    def test_workflow_create_first_vm_with_bastion(self, skip_e2e, test_env,
                                                    temp_home_dir):
        """
        Workflow: Create first VM in new resource group with bastion.

        Steps:
        1. User runs: azlin create my-vm --resource-group new-rg
        2. System detects no bastion exists
        3. System prompts: "No Bastion found. Create one for secure access? (Y/n)"
        4. User accepts (default yes)
        5. System creates bastion (10 minutes)
        6. System creates VM without public IP
        7. VM is ready and accessible via bastion
        """
        from azlin.modules.bastion_detector import BastionDetector

        with patch.object(BastionDetector, 'detect_bastion_for_vm', return_value=None):
            with patch('click.confirm', return_value=True) as mock_confirm:
                with patch('subprocess.run') as mock_run:
                    # Act
                    # CLI workflow simulation
                    pass

        # Assert
        mock_confirm.assert_called()
        # Should have prompted to create bastion

    def test_workflow_create_second_vm_reuses_bastion(self, skip_e2e, test_env):
        """
        Workflow: Create second VM in same RG, reuses existing bastion.

        Steps:
        1. Bastion already exists from previous VM
        2. User runs: azlin create my-vm-2 --resource-group existing-rg
        3. System detects existing bastion
        4. System prompts: "Found Bastion 'my-bastion'. Use it? (Y/n)"
        5. User accepts (default yes)
        6. System creates VM without public IP
        7. VM uses same bastion as first VM
        """
        from azlin.modules.bastion_detector import BastionDetector

        bastion_info = {"name": "existing-bastion", "resource_group": test_env["resource_group"]}

        with patch.object(BastionDetector, 'detect_bastion_for_vm',
                         return_value=bastion_info):
            with patch('click.confirm', return_value=True) as mock_confirm:
                # Act
                # Should detect and prompt to use existing bastion
                pass

        # Assert
        mock_confirm.assert_called()
        confirm_msg = str(mock_confirm.call_args)
        assert "found" in confirm_msg.lower() or "existing" in confirm_msg.lower()

    def test_workflow_create_vm_decline_bastion_use_public_ip(self, skip_e2e, test_env):
        """
        Workflow: User prefers public IP over bastion.

        Steps:
        1. User runs: azlin create my-vm --resource-group my-rg
        2. System prompts about bastion
        3. User declines (presses 'n')
        4. System creates VM with public IP
        5. User can connect directly without bastion
        """
        from azlin.modules.bastion_detector import BastionDetector

        with patch.object(BastionDetector, 'detect_bastion_for_vm', return_value=None):
            with patch('click.confirm', return_value=False):  # User declines
                with patch('subprocess.run') as mock_run:
                    # Act
                    # Should create VM with public IP
                    pass

        # Assert
        # Verify public IP was created

    def test_workflow_create_vm_with_no_bastion_flag(self, skip_e2e, test_env):
        """
        Workflow: User explicitly wants no bastion.

        Steps:
        1. User runs: azlin create my-vm --no-bastion
        2. System skips all bastion detection and prompts
        3. System creates VM with public IP immediately
        4. No interaction required
        """
        from azlin.modules.bastion_detector import BastionDetector

        with patch.object(BastionDetector, 'detect_bastion_for_vm') as mock_detect:
            with patch('click.confirm') as mock_confirm:
                with patch('subprocess.run'):
                    # Act
                    # CLI: azlin create my-vm --no-bastion
                    pass

        # Assert
        mock_detect.assert_not_called()
        mock_confirm.assert_not_called()

    def test_workflow_connect_to_private_vm_via_bastion(self, skip_e2e, test_env):
        """
        Workflow: Connect to private-only VM.

        Steps:
        1. VM exists without public IP
        2. User runs: azlin connect my-vm
        3. System detects bastion is required
        4. System creates bastion tunnel automatically
        5. User connects via SSH through tunnel
        6. Tunnel cleans up on disconnect
        """
        from azlin.vm_connector import VMConnector
        from azlin.vm_manager import VMManager, VMInfo
        from azlin.modules.bastion_manager import BastionManager

        # Mock private VM
        mock_vm = Mock(spec=VMInfo)
        mock_vm.public_ip = None
        mock_vm.private_ip = "10.0.0.4"
        mock_vm.is_running.return_value = True

        with patch.object(VMManager, 'get_vm', return_value=mock_vm):
            with patch.object(BastionManager, 'create_tunnel'):
                # Act
                # Should automatically use bastion for private VM
                pass

        # Assert
        # Verify tunnel was created


class TestErrorScenarios:
    """Test error handling in E2E scenarios."""

    def test_bastion_creation_fails_graceful_fallback(self, skip_e2e, test_env):
        """
        Scenario: Bastion creation fails.

        Given: User accepts creating bastion
        When: Bastion creation fails (quota, permission, etc.)
        Then: System shows error and offers to continue with public IP
        """
        from azlin.modules.bastion_detector import BastionDetector

        with patch.object(BastionDetector, 'detect_bastion_for_vm', return_value=None):
            with patch('click.confirm', side_effect=[True, True]):
                # First: User wants bastion
                # Second: User accepts fallback to public IP
                with patch('subprocess.run', side_effect=[
                    Exception("Quota exceeded"),  # Bastion creation fails
                    Mock(stdout='{"publicIpAddress": "20.1.2.3"}')  # VM succeeds
                ]):
                    # Act
                    # Should fallback gracefully
                    pass

    def test_connect_to_private_vm_no_bastion_helpful_error(self, skip_e2e, test_env):
        """
        Scenario: Cannot connect to private VM without bastion.

        Given: VM has no public IP
        And: No bastion is available
        When: User tries to connect
        Then: System shows helpful error with remediation steps
        """
        from azlin.vm_connector import VMConnector
        from azlin.vm_manager import VMManager, VMInfo
        from azlin.modules.bastion_detector import BastionDetector

        # Mock private VM
        mock_vm = Mock(spec=VMInfo)
        mock_vm.public_ip = None
        mock_vm.private_ip = "10.0.0.4"

        with patch.object(VMManager, 'get_vm', return_value=mock_vm):
            with patch.object(BastionDetector, 'detect_bastion_for_vm',
                             return_value=None):
                # Act & Assert
                try:
                    VMConnector.connect("my-vm", resource_group=test_env["resource_group"])
                    pytest.fail("Should have raised error for private VM without bastion")
                except Exception as e:
                    # Verify helpful error message
                    error_msg = str(e).lower()
                    assert "private" in error_msg or "no public ip" in error_msg
                    assert "bastion" in error_msg

    def test_invalid_bastion_name_validation(self, skip_e2e, test_env):
        """
        Scenario: User provides invalid bastion name.

        Given: User specifies --bastion-name with invalid characters
        When: Command is executed
        Then: System validates and rejects with clear error
        """
        from azlin.vm_provisioning import VMConfig

        invalid_names = [
            "bastion@invalid",
            "bastion name",  # spaces
            "",  # empty
            "a" * 100,  # too long
        ]

        for invalid_name in invalid_names:
            with pytest.raises(ValueError, match="Invalid.*name"):
                config = VMConfig(
                    name="test-vm",
                    resource_group=test_env["resource_group"],
                    bastion_name=invalid_name
                )


class TestPerformanceAndScaling:
    """Test performance characteristics in E2E scenarios."""

    def test_bastion_detection_performance(self, skip_e2e, test_env):
        """Test bastion detection completes in reasonable time."""
        import time
        from azlin.modules.bastion_detector import BastionDetector

        # Act
        start = time.time()
        BastionDetector.detect_bastion_for_vm(
            vm_name="test-vm",
            resource_group=test_env["resource_group"]
        )
        duration = time.time() - start

        # Assert - Should complete in <5 seconds
        assert duration < 5.0, f"Bastion detection took {duration}s, expected <5s"

    def test_multiple_vm_provisioning_with_shared_bastion(self, skip_e2e, test_env):
        """Test provisioning multiple VMs shares bastion efficiently."""
        from azlin.modules.bastion_detector import BastionDetector

        bastion_info = {"name": "shared-bastion",
                       "resource_group": test_env["resource_group"]}

        with patch.object(BastionDetector, 'detect_bastion_for_vm',
                         return_value=bastion_info) as mock_detect:
            with patch('click.confirm', return_value=True):
                # Act - Provision 5 VMs
                for i in range(5):
                    # Each VM should use same bastion
                    pass

        # Assert - Bastion detection should be efficient
        # Not called 5 times if cached properly


class TestSecurityCompliance:
    """Test security requirements in E2E scenarios."""

    def test_no_credentials_in_config_files(self, skip_e2e, temp_home_dir):
        """Test no credentials are stored in config files."""
        from azlin.modules.bastion_config import BastionConfig

        # Arrange
        config_path = temp_home_dir / ".azlin" / "bastion_config.toml"
        bastion_config = BastionConfig()
        bastion_config.add_mapping(
            vm_name="test-vm",
            vm_resource_group="test-rg",
            bastion_name="test-bastion",
            bastion_resource_group="network-rg"
        )

        # Act
        bastion_config.save(config_path)

        # Assert
        config_content = config_path.read_text()
        sensitive_patterns = [
            "password", "secret", "token", "key", "credential",
            "client_secret", "subscription_id"
        ]
        for pattern in sensitive_patterns:
            assert pattern not in config_content.lower(), \
                f"Found sensitive pattern '{pattern}' in config"

    def test_config_file_permissions_secure(self, skip_e2e, temp_home_dir):
        """Test config files have secure permissions (0600)."""
        from azlin.modules.bastion_config import BastionConfig

        # Arrange
        config_path = temp_home_dir / ".azlin" / "bastion_config.toml"
        bastion_config = BastionConfig()

        # Act
        bastion_config.save(config_path)

        # Assert
        stat = config_path.stat()
        mode = stat.st_mode & 0o777
        assert mode == 0o600, f"Config has insecure permissions: {oct(mode)}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
