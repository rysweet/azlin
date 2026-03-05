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


class TestTmuxConfMerge:
    """Test tmux.conf merge behavior during cloud-init generation."""

    def test_cloud_init_includes_azlin_tmux_defaults(self):
        """Cloud-init includes azlin tmux defaults when no user config exists.

        Given: No user .tmux.conf on the local machine
        When: _generate_cloud_init is called
        Then: Cloud-init contains azlin default status bar settings
        """
        provisioner = VMProvisioner()
        cloud_init = provisioner._generate_cloud_init()

        assert "AZLIN DEFAULTS" in cloud_init
        assert "set -g status-left-length 50" in cloud_init
        assert "set -g status-bg black" in cloud_init

    def test_cloud_init_without_user_tmux_conf(self, tmp_path, monkeypatch):
        """Cloud-init has no USER SETTINGS section when no user config exists.

        Given: No user .tmux.conf files
        When: _generate_cloud_init is called
        Then: Cloud-init does NOT contain the user settings marker
        """
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        provisioner = VMProvisioner()
        cloud_init = provisioner._generate_cloud_init()

        assert "USER SETTINGS" not in cloud_init

    def test_build_tmux_conf_defaults_only(self):
        """_build_tmux_conf_content returns only defaults when no user config provided.

        Given: No user config (None)
        When: _build_tmux_conf_content is called
        Then: Returns azlin defaults without user section
        """
        provisioner = VMProvisioner()
        result = provisioner._build_tmux_conf_content(None)

        assert "AZLIN DEFAULTS" in result
        assert "set -g status-left-length 50" in result
        assert "USER SETTINGS" not in result

    def test_build_tmux_conf_with_user_settings(self):
        """_build_tmux_conf_content merges user settings after azlin defaults.

        Given: User tmux.conf content
        When: _build_tmux_conf_content is called
        Then: Returns azlin defaults followed by user settings
        """
        provisioner = VMProvisioner()
        user_conf = "set -g mouse on\nset -g history-limit 50000"
        result = provisioner._build_tmux_conf_content(user_conf)

        assert "AZLIN DEFAULTS" in result
        assert "USER SETTINGS" in result
        assert "set -g mouse on" in result
        assert "set -g history-limit 50000" in result

        # Azlin defaults come before user settings
        defaults_pos = result.find("AZLIN DEFAULTS")
        user_pos = result.find("USER SETTINGS")
        assert defaults_pos < user_pos

    def test_build_tmux_conf_user_overrides_take_effect(self):
        """User settings placed after defaults so tmux last-wins applies.

        Given: User config that overrides a default setting
        When: _build_tmux_conf_content is called
        Then: User's override appears after the default
        """
        provisioner = VMProvisioner()
        user_conf = "set -g status-bg red"
        result = provisioner._build_tmux_conf_content(user_conf)

        default_bg_pos = result.find("set -g status-bg black")
        user_bg_pos = result.find("set -g status-bg red")
        assert default_bg_pos < user_bg_pos

    def test_build_tmux_conf_strips_trailing_whitespace(self):
        """Trailing whitespace in user config is stripped.

        Given: User config with trailing newlines
        When: _build_tmux_conf_content is called
        Then: Trailing whitespace is removed
        """
        provisioner = VMProvisioner()
        user_conf = "set -g mouse on\n\n\n"
        result = provisioner._build_tmux_conf_content(user_conf)

        assert result.endswith("set -g mouse on")

    def test_get_user_tmux_conf_returns_none_when_no_files(self, tmp_path, monkeypatch):
        """_get_user_tmux_conf returns None when no user tmux.conf exists.

        Given: Neither ~/.azlin/home/.tmux.conf nor ~/.tmux.conf exist
        When: _get_user_tmux_conf is called
        Then: Returns None
        """
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        provisioner = VMProvisioner()

        assert provisioner._get_user_tmux_conf() is None

    def test_get_user_tmux_conf_prefers_azlin_home(self, tmp_path, monkeypatch):
        """_get_user_tmux_conf prefers ~/.azlin/home/.tmux.conf over ~/.tmux.conf.

        Given: Both ~/.azlin/home/.tmux.conf and ~/.tmux.conf exist
        When: _get_user_tmux_conf is called
        Then: Returns content from ~/.azlin/home/.tmux.conf
        """
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)

        # Create both files with different content
        azlin_dir = tmp_path / ".azlin" / "home"
        azlin_dir.mkdir(parents=True)
        (azlin_dir / ".tmux.conf").write_text("# azlin home version")
        (tmp_path / ".tmux.conf").write_text("# home version")

        provisioner = VMProvisioner()
        result = provisioner._get_user_tmux_conf()

        assert result == "# azlin home version"

    def test_get_user_tmux_conf_falls_back_to_home(self, tmp_path, monkeypatch):
        """_get_user_tmux_conf falls back to ~/.tmux.conf when azlin dir absent.

        Given: Only ~/.tmux.conf exists (no ~/.azlin/home/.tmux.conf)
        When: _get_user_tmux_conf is called
        Then: Returns content from ~/.tmux.conf
        """
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        (tmp_path / ".tmux.conf").write_text("# home version")

        provisioner = VMProvisioner()
        result = provisioner._get_user_tmux_conf()

        assert result == "# home version"

    def test_get_user_tmux_conf_warns_on_large_file(self, tmp_path, monkeypatch, caplog):
        """_get_user_tmux_conf logs warning for large files.

        Given: A .tmux.conf larger than 8KB
        When: _get_user_tmux_conf is called
        Then: Warning is logged about cloud-init size limit
        """
        import logging

        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        (tmp_path / ".tmux.conf").write_text("x" * 9000)

        provisioner = VMProvisioner()
        with caplog.at_level(logging.WARNING):
            result = provisioner._get_user_tmux_conf()

        assert result is not None
        assert "large" in caplog.text.lower() or "9000" in caplog.text

    def test_cloud_init_with_user_tmux_is_valid_yaml(self, tmp_path, monkeypatch):
        """Cloud-init with merged tmux.conf is still valid YAML.

        Given: A user .tmux.conf with various settings
        When: _generate_cloud_init is called
        Then: The output is valid YAML with proper runcmd entries
        """
        import yaml

        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        (tmp_path / ".tmux.conf").write_text(
            "set -g mouse on\nset -g history-limit 50000\nbind r source-file ~/.tmux.conf"
        )

        provisioner = VMProvisioner()
        cloud_init = provisioner._generate_cloud_init()

        data = yaml.safe_load(cloud_init)
        runcmd = data.get("runcmd", [])
        assert len(runcmd) > 0
        for i, entry in enumerate(runcmd):
            assert not isinstance(entry, dict), f"runcmd[{i}] is a dict (YAML mapping bug): {entry}"

    def test_cloud_init_merged_tmux_contains_both_sections(self, tmp_path, monkeypatch):
        """Cloud-init with user config has both AZLIN DEFAULTS and USER SETTINGS.

        Given: A user .tmux.conf exists
        When: _generate_cloud_init is called
        Then: Cloud-init contains both section markers and user content
        """
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        (tmp_path / ".tmux.conf").write_text("set -g mouse on")

        provisioner = VMProvisioner()
        cloud_init = provisioner._generate_cloud_init()

        assert "AZLIN DEFAULTS" in cloud_init
        assert "USER SETTINGS" in cloud_init
        assert "set -g mouse on" in cloud_init

    def test_get_user_tmux_conf_rejects_symlink_outside_home(self, tmp_path, monkeypatch, caplog):
        """Symlinks pointing outside home directory are rejected.

        Given: .tmux.conf is a symlink to /etc/passwd
        When: _get_user_tmux_conf is called
        Then: Returns None and logs a warning
        """
        import logging

        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        tmux_link = tmp_path / ".tmux.conf"
        tmux_link.symlink_to("/etc/passwd")

        provisioner = VMProvisioner()
        with caplog.at_level(logging.WARNING):
            result = provisioner._get_user_tmux_conf()

        assert result is None
        assert "symlink" in caplog.text.lower()

    def test_get_user_tmux_conf_handles_non_utf8(self, tmp_path, monkeypatch, caplog):
        """Non-UTF8 files are skipped gracefully.

        Given: .tmux.conf contains binary data
        When: _get_user_tmux_conf is called
        Then: Returns None and logs a warning
        """
        import logging

        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        (tmp_path / ".tmux.conf").write_bytes(b"\xff\xfe binary content")

        provisioner = VMProvisioner()
        with caplog.at_level(logging.WARNING):
            result = provisioner._get_user_tmux_conf()

        assert result is None
        assert "failed to read" in caplog.text.lower()

    def test_build_tmux_conf_ignores_whitespace_only_user_conf(self):
        """Whitespace-only user config is treated as no config.

        Given: User config with only whitespace
        When: _build_tmux_conf_content is called
        Then: Returns azlin defaults without user section
        """
        provisioner = VMProvisioner()
        result = provisioner._build_tmux_conf_content("   \n\n  ")

        assert "AZLIN DEFAULTS" in result
        assert "USER SETTINGS" not in result

    def test_get_user_tmux_conf_allows_symlink_within_home(self, tmp_path, monkeypatch):
        """Symlinks within home directory are allowed.

        Given: .tmux.conf is a symlink to another file under ~/
        When: _get_user_tmux_conf is called
        Then: Returns the file content
        """
        monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
        real_conf = tmp_path / "dotfiles" / "tmux.conf"
        real_conf.parent.mkdir()
        real_conf.write_text("set -g mouse on")
        (tmp_path / ".tmux.conf").symlink_to(real_conf)

        provisioner = VMProvisioner()
        result = provisioner._get_user_tmux_conf()

        assert result == "set -g mouse on"
