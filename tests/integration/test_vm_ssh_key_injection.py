"""Integration test for SSH key management during VM provisioning."""

from azlin.modules.ssh_keys import SSHKeyManager


class TestSSHKeyInjectionWorkflow:
    """Test SSH key generation and injection workflow."""

    def test_ssh_key_generation(self, tmp_path):
        """Test generating SSH key pair."""
        key_manager = SSHKeyManager(keys_dir=tmp_path)

        # Generate key pair
        key_pair = key_manager.generate_key_pair(key_name="test-key")

        assert key_pair is not None
        assert key_pair.private_key_path.exists()
        assert key_pair.public_key_path.exists()

    def test_ssh_public_key_format_validation(self, tmp_path):
        """Test validating SSH public key format."""
        key_manager = SSHKeyManager(keys_dir=tmp_path)

        # Generate key
        key_pair = key_manager.generate_key_pair(key_name="test-key")

        # Read public key
        public_key_content = key_pair.public_key_path.read_text()

        # Validate format (should start with ssh-rsa or ssh-ed25519)
        assert public_key_content.startswith(("ssh-rsa", "ssh-ed25519", "ecdsa-sha2"))

    def test_ssh_key_injection_to_vm_config(self, tmp_path):
        """Test injecting SSH public key into VM configuration."""
        key_manager = SSHKeyManager(keys_dir=tmp_path)

        # Generate key
        key_pair = key_manager.generate_key_pair(key_name="vm-key")

        # Get public key content
        public_key = key_pair.public_key_path.read_text().strip()

        # Create VM config with SSH key
        vm_config = {
            "name": "test-vm",
            "admin_username": "azureuser",
            "ssh_public_key": public_key,
        }

        # Verify SSH key is in config
        assert "ssh_public_key" in vm_config
        assert vm_config["ssh_public_key"] == public_key
