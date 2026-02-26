"""Unit tests for VM provisioning cloud-init generation.

This module tests the _generate_cloud_init method to ensure:
1. Required packages are included in cloud-init
2. pip and pipx are installed via packages section
3. Cloud-init structure is valid

Test Philosophy:
- Comprehensive coverage of cloud-init content
- Verify all critical packages are present
- Ensure cloud-init YAML is well-formed
- Test with and without SSH keys
"""

from azlin.vm_provisioning import VMProvisioner


class TestGenerateCloudInit:
    """Test _generate_cloud_init() method."""

    def test_cloud_init_includes_pip(self):
        """Test that cloud-init includes python3-pip package.

        Given: A VMProvisioner instance
        When: _generate_cloud_init is called
        Then: Returns cloud-init containing python3-pip
        """
        provisioner = VMProvisioner()
        cloud_init = provisioner._generate_cloud_init()

        assert "python3-pip" in cloud_init
        assert "packages:" in cloud_init

    def test_cloud_init_includes_pipx(self):
        """Test that cloud-init includes pipx package.

        Given: A VMProvisioner instance
        When: _generate_cloud_init is called
        Then: Returns cloud-init containing pipx
        """
        provisioner = VMProvisioner()
        cloud_init = provisioner._generate_cloud_init()

        assert "pipx" in cloud_init
        assert "packages:" in cloud_init

    def test_cloud_init_includes_all_required_packages(self):
        """Test that cloud-init includes all required packages.

        Given: A VMProvisioner instance
        When: _generate_cloud_init is called
        Then: Returns cloud-init containing all essential packages
        """
        provisioner = VMProvisioner()
        cloud_init = provisioner._generate_cloud_init()

        # Essential packages that must be present
        required_packages = [
            "docker.io",
            "git",
            "tmux",
            "curl",
            "wget",
            "build-essential",
            "software-properties-common",
            "ripgrep",
            "python3-pip",
            "pipx",
        ]

        for package in required_packages:
            assert package in cloud_init, f"Required package '{package}' not found in cloud-init"

    def test_cloud_init_has_valid_structure(self):
        """Test that cloud-init has valid YAML structure.

        Given: A VMProvisioner instance
        When: _generate_cloud_init is called
        Then: Returns cloud-init starting with #cloud-config
        """
        provisioner = VMProvisioner()
        cloud_init = provisioner._generate_cloud_init()

        assert cloud_init.startswith("#cloud-config")
        assert "package_update: true" in cloud_init
        assert "package_upgrade: true" in cloud_init
        assert "packages:" in cloud_init
        assert "runcmd:" in cloud_init

    def test_cloud_init_with_ssh_key(self):
        """Test that cloud-init includes SSH key when provided.

        Given: A VMProvisioner instance and SSH public key
        When: _generate_cloud_init is called with SSH key
        Then: Returns cloud-init containing ssh_authorized_keys section
        """
        provisioner = VMProvisioner()
        ssh_key = "ssh-rsa AAAAB3NzaC1yc2EAAAADAQABAAABAQC... test@example.com"
        cloud_init = provisioner._generate_cloud_init(ssh_public_key=ssh_key)

        assert "ssh_authorized_keys:" in cloud_init
        assert ssh_key in cloud_init

    def test_cloud_init_without_ssh_key(self):
        """Test that cloud-init works without SSH key.

        Given: A VMProvisioner instance without SSH key
        When: _generate_cloud_init is called without SSH key
        Then: Returns cloud-init without ssh_authorized_keys section
        """
        provisioner = VMProvisioner()
        cloud_init = provisioner._generate_cloud_init(ssh_public_key=None)

        assert "ssh_authorized_keys:" not in cloud_init
        # But packages should still be present
        assert "python3-pip" in cloud_init
        assert "pipx" in cloud_init

    def test_cloud_init_includes_python_setup(self):
        """Test that cloud-init includes conditional Python 3.13+ setup.

        Given: A VMProvisioner instance
        When: _generate_cloud_init is called
        Then: Returns cloud-init with conditional deadsnakes PPA (skipped on 25.10+)
        """
        provisioner = VMProvisioner()
        cloud_init = provisioner._generate_cloud_init()

        assert "python3.13" in cloud_init
        assert "deadsnakes/ppa" in cloud_init
        # Deadsnakes is conditional: only added when Python 3.13+ not already present
        assert "python3 --version" in cloud_init
        assert "skipping deadsnakes PPA" in cloud_init

    def test_cloud_init_uses_node22_lts(self):
        """Test that cloud-init uses Node.js 22 LTS (not 20).

        Given: A VMProvisioner instance
        When: _generate_cloud_init is called
        Then: Uses NodeSource setup_22.x for Node.js 22 LTS
        """
        provisioner = VMProvisioner()
        cloud_init = provisioner._generate_cloud_init()

        assert "setup_22.x" in cloud_init
        assert "setup_20.x" not in cloud_init

    def test_cloud_init_reinstalls_ripgrep_after_upgrade(self):
        """Test that ripgrep is re-installed after apt full-upgrade.

        Given: A VMProvisioner instance
        When: _generate_cloud_init is called
        Then: ripgrep appears both in packages and after full-upgrade in runcmd
        """
        provisioner = VMProvisioner()
        cloud_init = provisioner._generate_cloud_init()

        # ripgrep in packages section
        packages_pos = cloud_init.find("packages:")
        runcmd_pos = cloud_init.find("runcmd:")
        ripgrep_pkg_pos = cloud_init.find("  - ripgrep")
        assert packages_pos < ripgrep_pkg_pos < runcmd_pos

        # ripgrep reinstalled in runcmd after full-upgrade
        full_upgrade_pos = cloud_init.find("apt full-upgrade")
        ripgrep_reinstall_pos = cloud_init.find("apt install -y ripgrep")
        assert ripgrep_reinstall_pos > full_upgrade_pos

    def test_cloud_init_includes_docker_setup(self):
        """Test that cloud-init includes Docker setup.

        Given: A VMProvisioner instance
        When: _generate_cloud_init is called
        Then: Returns cloud-init containing Docker configuration
        """
        provisioner = VMProvisioner()
        cloud_init = provisioner._generate_cloud_init()

        assert "docker" in cloud_init.lower()
        assert "usermod -aG docker" in cloud_init

    def test_cloud_init_includes_uv_package_manager(self):
        """Test that cloud-init includes astral-uv (uv) installation.

        Given: A VMProvisioner instance
        When: _generate_cloud_init is called
        Then: Returns cloud-init containing astral-uv installation
        """
        provisioner = VMProvisioner()
        cloud_init = provisioner._generate_cloud_init()

        assert "astral-uv" in cloud_init

    def test_cloud_init_includes_github_cli(self):
        """Test that cloud-init includes GitHub CLI setup.

        Given: A VMProvisioner instance
        When: _generate_cloud_init is called
        Then: Returns cloud-init containing gh CLI installation
        """
        provisioner = VMProvisioner()
        cloud_init = provisioner._generate_cloud_init()

        assert "gh" in cloud_init
        assert "github.com/packages" in cloud_init

    def test_cloud_init_includes_final_message(self):
        """Test that cloud-init includes completion message.

        Given: A VMProvisioner instance
        When: _generate_cloud_init is called
        Then: Returns cloud-init containing final_message
        """
        provisioner = VMProvisioner()
        cloud_init = provisioner._generate_cloud_init()

        assert "final_message:" in cloud_init
        assert "azlin VM provisioning complete" in cloud_init


class TestCloudInitPackageOrder:
    """Test that packages are in logical order."""

    def test_pip_and_pipx_are_in_packages_section(self):
        """Test that pip and pipx are in the packages section, not runcmd.

        Given: A VMProvisioner instance
        When: _generate_cloud_init is called
        Then: pip and pipx appear in packages section before runcmd
        """
        provisioner = VMProvisioner()
        cloud_init = provisioner._generate_cloud_init()

        # Find positions
        packages_pos = cloud_init.find("packages:")
        runcmd_pos = cloud_init.find("runcmd:")
        pip_pos = cloud_init.find("python3-pip")
        pipx_pos = cloud_init.find("pipx")

        # Verify structure
        assert packages_pos < runcmd_pos, "packages section should come before runcmd"
        assert packages_pos < pip_pos < runcmd_pos, "python3-pip should be in packages section"
        assert packages_pos < pipx_pos < runcmd_pos, "pipx should be in packages section"

    def test_packages_section_has_correct_yaml_formatting(self):
        """Test that packages are formatted as YAML list items.

        Given: A VMProvisioner instance
        When: _generate_cloud_init is called
        Then: Each package is formatted as '  - packagename'
        """
        provisioner = VMProvisioner()
        cloud_init = provisioner._generate_cloud_init()

        # Check for proper YAML list formatting
        assert "  - python3-pip" in cloud_init
        assert "  - pipx" in cloud_init
        assert "  - ripgrep" in cloud_init
        assert "  - docker.io" in cloud_init


class TestSystemUpgrade:
    """Test full system upgrade in cloud-init."""

    def test_full_upgrade_present(self):
        """Test that cloud-init includes full system upgrade.

        Given: A VMProvisioner instance
        When: _generate_cloud_init is called
        Then: Returns cloud-init containing apt full-upgrade commands
        """
        provisioner = VMProvisioner()
        cloud_init = provisioner._generate_cloud_init()

        assert "apt full-upgrade -y" in cloud_init
        assert "apt autoremove -y" in cloud_init
        assert "apt autoclean -y" in cloud_init

    def test_full_upgrade_runs_early(self):
        """Test that full system upgrade runs before package installs.

        Given: A VMProvisioner instance
        When: _generate_cloud_init is called
        Then: full-upgrade appears before Python/gh install commands
        """
        provisioner = VMProvisioner()
        cloud_init = provisioner._generate_cloud_init()

        upgrade_pos = cloud_init.find("apt full-upgrade")
        python_pos = cloud_init.find("python3.13")
        assert upgrade_pos < python_pos, "full-upgrade should run before Python install"


class TestVersionLogging:
    """Test version logging commands in cloud-init."""

    def test_version_logging_commands_present(self):
        """Test that npm and rg version logging exists in runcmd section with correct format."""
        provisioner = VMProvisioner()
        cloud_init = provisioner._generate_cloud_init()

        # Verify both version commands exist in runcmd section with correct format
        assert "runcmd:" in cloud_init, "runcmd section not found"
        runcmd_pos = cloud_init.find("runcmd:")

        # Check npm version logging
        npm_pos = cloud_init.find("[AZLIN_VERSION] npm=")
        assert npm_pos > runcmd_pos, "npm version logging not in runcmd section"
        assert "npm --version" in cloud_init, "npm --version command not found"

        # Check rg version logging
        rg_pos = cloud_init.find("[AZLIN_VERSION] rg=")
        assert rg_pos > runcmd_pos, "rg version logging not in runcmd section"
        assert "rg --version" in cloud_init, "rg --version command not found"

    def test_cloud_init_runcmd_entries_are_valid_yaml_strings(self):
        """Ensure runcmd entries are strings or lists, never dicts (YAML mapping bug guard)."""
        import yaml

        provisioner = VMProvisioner()
        cloud_init = provisioner._generate_cloud_init(
            ssh_public_key="ssh-rsa TESTKEY", has_home_disk=False, has_tmp_disk=False
        )
        data = yaml.safe_load(cloud_init)
        runcmd = data.get("runcmd", [])
        assert len(runcmd) > 0, "runcmd should not be empty"
        for i, entry in enumerate(runcmd):
            assert not isinstance(entry, dict), (
                f"runcmd[{i}] is a dict (YAML colon-space in unquoted string?): {entry}"
            )
