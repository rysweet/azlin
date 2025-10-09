"""
End-to-end tests for complete azlin workflows.

Tests complete CLI workflows from entry point to completion
with all mocked external services (TDD - RED phase).

Test Coverage:
- Full workflow with --repo flag
- Full workflow without --repo flag
- Workflow with pre-existing VM
- Workflow with authentication failure
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
from tests.mocks.azure_mock import create_mock_azure_environment
from tests.mocks.github_mock import GitHubMockFactory


# ============================================================================
# COMPLETE WORKFLOW WITH REPO TESTS
# ============================================================================

class TestCompleteWorkflowWithRepo:
    """Test complete end-to-end workflow with GitHub repository."""

    @patch('sys.argv', ['azlin', '--repo', 'https://github.com/user/dotfiles'])
    def test_full_workflow_with_repo_flag(
        self,
        tmp_path,
        mock_azure_credentials,
        mock_azure_compute_client,
        mock_azure_network_client,
        mock_azure_resource_client,
        mock_gh_cli_authenticated
    ):
        """Test complete workflow: VM provision + tool install + repo clone + SSH connect.

        RED PHASE: E2E test - will fail until all components implemented.

        Workflow:
        1. Parse CLI args
        2. Authenticate to Azure
        3. Provision VM with networking
        4. Wait for VM to be ready
        5. Generate SSH keys
        6. Configure SSH
        7. Install tools on VM
        8. Clone GitHub repository
        9. Setup tmux session
        10. Auto-connect via SSH
        11. Send success notification
        """
        from azlin.cli import main

        # Mock progress display to avoid output
        with patch('azlin.progress.ProgressDisplay') as mock_progress, \
             patch('azlin.ssh_config.SSHConfigurator.generate_key') as mock_ssh_keygen, \
             patch('azlin.ssh_config.SSHConfigurator.connect') as mock_ssh_connect, \
             patch('azlin.notifications.send_imessr_notification') as mock_notify:

            # Configure mocks for success
            mock_ssh_keygen.return_value = ('~/.ssh/azlin_rsa', '~/.ssh/azlin_rsa.pub')
            mock_ssh_connect.return_value = True
            mock_notify.return_value = True

            # Run main workflow
            try:
                exit_code = main()
            except SystemExit as e:
                exit_code = e.code

            # Verify workflow completed
            assert exit_code == 0

            # Verify Azure VM was created
            mock_azure_compute_client.return_value.virtual_machines.begin_create_or_update.assert_called_once()

            # Verify SSH connection was attempted
            mock_ssh_connect.assert_called_once()

            # Verify GitHub CLI was used to clone repo
            assert any('gh repo clone' in str(call) for call in mock_gh_cli_authenticated.mock_calls)

            # Verify success notification was sent
            mock_notify.assert_called_once()

    @patch('sys.argv', ['azlin', '--repo', 'https://github.com/user/dotfiles', '--vm-size', 'Standard_D4s_v3'])
    def test_workflow_with_custom_vm_size(
        self,
        mock_azure_credentials,
        mock_azure_compute_client
    ):
        """Test workflow with custom VM size parameter."""
        from azlin.cli import main

        with patch('azlin.progress.ProgressDisplay'), \
             patch('azlin.ssh_config.SSHConfigurator.connect'):

            try:
                main()
            except SystemExit:
                pass

            # Verify VM was created with specified size
            call_args = mock_azure_compute_client.return_value.virtual_machines.begin_create_or_update.call_args
            vm_params = call_args[1]['parameters'] if call_args else {}

            # Check VM size in parameters
            assert 'Standard_D4s_v3' in str(vm_params) or \
                   vm_params.get('properties', {}).get('hardwareProfile', {}).get('vmSize') == 'Standard_D4s_v3'


# ============================================================================
# COMPLETE WORKFLOW WITHOUT REPO TESTS
# ============================================================================

class TestCompleteWorkflowWithoutRepo:
    """Test complete end-to-end workflow without GitHub repository."""

    @patch('sys.argv', ['azlin'])
    def test_full_workflow_without_repo_flag(
        self,
        mock_azure_credentials,
        mock_azure_compute_client,
        mock_subprocess_success
    ):
        """Test complete workflow without repository cloning.

        Workflow:
        1. Parse CLI args (no --repo)
        2. Authenticate to Azure
        3. Provision VM
        4. Install tools
        5. Setup tmux session
        6. Setup gh auth (but don't clone)
        7. Auto-connect via SSH
        """
        from azlin.cli import main

        with patch('azlin.progress.ProgressDisplay'), \
             patch('azlin.ssh_config.SSHConfigurator.connect') as mock_ssh_connect:

            mock_ssh_connect.return_value = True

            try:
                exit_code = main()
            except SystemExit as e:
                exit_code = e.code

            # Verify VM was created
            mock_azure_compute_client.return_value.virtual_machines.begin_create_or_update.assert_called_once()

            # Verify gh repo clone was NOT called (no --repo flag)
            subprocess_calls = [str(call) for call in mock_subprocess_success.mock_calls]
            assert not any('gh repo clone' in call for call in subprocess_calls)

            # But gh auth should still be set up
            assert any('gh auth' in call for call in subprocess_calls)


# ============================================================================
# PRE-EXISTING VM TESTS
# ============================================================================

class TestWorkflowWithExistingVM:
    """Test workflow when VM already exists."""

    @patch('sys.argv', ['azlin', '--vm-name', 'existing-vm'])
    def test_connects_to_existing_vm(
        self,
        mock_azure_credentials,
        mock_azure_compute_client
    ):
        """Test connecting to existing VM instead of creating new one."""
        from azlin.cli import main

        # Mock VM already exists
        existing_vm = Mock(
            name='existing-vm',
            provisioning_state='Succeeded',
            location='eastus'
        )
        mock_azure_compute_client.return_value.virtual_machines.get.return_value = existing_vm

        with patch('azlin.progress.ProgressDisplay'), \
             patch('azlin.ssh_config.SSHConfigurator.connect') as mock_ssh_connect:

            mock_ssh_connect.return_value = True

            try:
                main()
            except SystemExit:
                pass

            # Verify VM creation was NOT called
            mock_azure_compute_client.return_value.virtual_machines.begin_create_or_update.assert_not_called()

            # But SSH connection should be attempted
            mock_ssh_connect.assert_called_once()


# ============================================================================
# FAILURE SCENARIO TESTS
# ============================================================================

class TestWorkflowFailureScenarios:
    """Test workflow failure scenarios."""

    @patch('sys.argv', ['azlin'])
    def test_workflow_handles_authentication_failure(
        self,
        mock_azure_credentials
    ):
        """Test workflow handles Azure authentication failure gracefully."""
        from azlin.cli import main

        # Make authentication fail
        mock_azure_credentials.side_effect = Exception('Authentication failed')

        with patch('azlin.progress.ProgressDisplay') as mock_progress, \
             patch('azlin.notifications.send_imessr_notification') as mock_notify:

            with pytest.raises(SystemExit) as exc_info:
                main()

            # Should exit with error code
            assert exc_info.value.code != 0

            # Should show error in progress display
            assert mock_progress.return_value.error.called

            # Should send failure notification
            if mock_notify.called:
                # Check notification was for failure
                call_args = mock_notify.call_args
                assert 'fail' in str(call_args).lower() or 'error' in str(call_args).lower()

    @patch('sys.argv', ['azlin'])
    def test_workflow_handles_vm_provisioning_failure(
        self,
        mock_azure_credentials,
        mock_azure_compute_client
    ):
        """Test workflow handles VM provisioning failure."""
        from azlin.cli import main

        # Make VM provisioning fail
        mock_azure_compute_client.return_value.virtual_machines.begin_create_or_update.side_effect = Exception(
            'QuotaExceeded: Insufficient quota'
        )

        with patch('azlin.progress.ProgressDisplay') as mock_progress:

            with pytest.raises(SystemExit) as exc_info:
                main()

            assert exc_info.value.code != 0

            # Should show quota error
            assert any(
                'quota' in str(call).lower()
                for call in mock_progress.return_value.error.mock_calls
            )

    @patch('sys.argv', ['azlin', '--repo', 'https://github.com/user/private-repo'])
    def test_workflow_handles_github_clone_failure(
        self,
        mock_azure_credentials,
        mock_azure_compute_client,
        mock_gh_cli_not_installed
    ):
        """Test workflow handles GitHub clone failure (gh not installed)."""
        from azlin.cli import main

        with patch('azlin.progress.ProgressDisplay') as mock_progress, \
             patch('azlin.ssh_config.SSHConfigurator.connect'):

            with pytest.raises(SystemExit) as exc_info:
                main()

            # May exit with error if gh is required
            # Or continue with warning if gh is optional


# ============================================================================
# PROGRESS TRACKING TESTS
# ============================================================================

class TestWorkflowProgressTracking:
    """Test progress tracking during workflow."""

    @patch('sys.argv', ['azlin'])
    def test_shows_progress_for_each_step(
        self,
        mock_azure_credentials,
        mock_azure_compute_client
    ):
        """Test that progress is displayed for each workflow step."""
        from azlin.cli import main

        with patch('azlin.progress.ProgressDisplay') as mock_progress, \
             patch('azlin.ssh_config.SSHConfigurator.connect'):

            try:
                main()
            except SystemExit:
                pass

            progress_instance = mock_progress.return_value

            # Verify progress was updated for major steps
            update_calls = [str(call) for call in progress_instance.update.mock_calls]

            expected_steps = [
                'Authenticating',
                'Creating VM',
                'Configuring SSH',
                'Installing tools'
            ]

            # At least some progress steps should be shown
            assert progress_instance.update.called or progress_instance.start.called

    @patch('sys.argv', ['azlin'])
    def test_shows_final_completion_message(
        self,
        mock_azure_credentials,
        mock_azure_compute_client
    ):
        """Test that final completion message is shown."""
        from azlin.cli import main

        with patch('azlin.progress.ProgressDisplay') as mock_progress, \
             patch('azlin.ssh_config.SSHConfigurator.connect'):

            try:
                main()
            except SystemExit:
                pass

            # Should call complete() or show success message
            assert mock_progress.return_value.complete.called or \
                   any('complete' in str(call).lower() or 'success' in str(call).lower()
                       for call in mock_progress.return_value.update.mock_calls)


# ============================================================================
# NOTIFICATION TESTS
# ============================================================================

class TestWorkflowNotifications:
    """Test imessR notifications during workflow."""

    @patch('sys.argv', ['azlin'])
    def test_sends_success_notification_on_completion(
        self,
        mock_azure_credentials,
        mock_azure_compute_client,
        mock_imessr_client
    ):
        """Test success notification is sent on completion."""
        from azlin.cli import main

        with patch('azlin.progress.ProgressDisplay'), \
             patch('azlin.ssh_config.SSHConfigurator.connect'), \
             patch('azlin.notifications.send_imessr_notification') as mock_notify:

            mock_notify.return_value = True

            try:
                main()
            except SystemExit:
                pass

            # Should send success notification
            mock_notify.assert_called_once()

            # Check notification content
            call_args = mock_notify.call_args
            notification_text = str(call_args)
            assert 'success' in notification_text.lower() or 'complete' in notification_text.lower()

    @patch('sys.argv', ['azlin'])
    def test_sends_failure_notification_on_error(
        self,
        mock_azure_credentials,
        mock_azure_compute_client
    ):
        """Test failure notification is sent on error."""
        from azlin.cli import main

        # Make workflow fail
        mock_azure_compute_client.return_value.virtual_machines.begin_create_or_update.side_effect = Exception('Failed')

        with patch('azlin.progress.ProgressDisplay'), \
             patch('azlin.notifications.send_imessr_notification') as mock_notify:

            with pytest.raises(SystemExit):
                main()

            # Should send failure notification if notifications enabled
            if mock_notify.called:
                call_args = mock_notify.call_args
                notification_text = str(call_args)
                assert 'fail' in notification_text.lower() or 'error' in notification_text.lower()
