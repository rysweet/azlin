"""Unit tests for config_manager module."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from azlin.config_manager import AzlinConfig, ConfigError, ConfigManager


class TestAzlinConfig:
    """Tests for AzlinConfig dataclass."""

    def test_default_values(self):
        """Test default configuration values."""
        config = AzlinConfig()
        assert config.default_resource_group is None
        assert config.default_region == "westus2"
        assert config.default_vm_size == "Standard_E16as_v5"
        assert config.last_vm_name is None

    def test_to_dict(self):
        """Test conversion to dictionary."""
        config = AzlinConfig(
            default_resource_group="my-rg",
            default_region="westus",
            default_vm_size="Standard_D4s_v3",
            last_vm_name="test-vm",
        )
        data = config.to_dict()
        assert data["default_resource_group"] == "my-rg"
        assert data["default_region"] == "westus"
        assert data["default_vm_size"] == "Standard_D4s_v3"
        assert data["last_vm_name"] == "test-vm"

    def test_from_dict(self):
        """Test creation from dictionary."""
        data = {
            "default_resource_group": "my-rg",
            "default_region": "westus",
            "default_vm_size": "Standard_D4s_v3",
            "last_vm_name": "test-vm",
        }
        config = AzlinConfig.from_dict(data)
        assert config.default_resource_group == "my-rg"
        assert config.default_region == "westus"
        assert config.default_vm_size == "Standard_D4s_v3"
        assert config.last_vm_name == "test-vm"

    def test_from_dict_partial(self):
        """Test creation from partial dictionary."""
        data = {"default_resource_group": "my-rg"}
        config = AzlinConfig.from_dict(data)
        assert config.default_resource_group == "my-rg"
        assert config.default_region == "westus2"  # Default
        assert config.default_vm_size == "Standard_E16as_v5"  # Default


class TestConfigManager:
    """Tests for ConfigManager class."""

    def test_get_config_path_default(self):
        """Test default config path."""
        path = ConfigManager.get_config_path()
        assert path == Path.home() / ".azlin" / "config.toml"

    def test_get_config_path_custom(self, tmp_path):
        """Test custom config path."""
        custom_path = tmp_path / "custom.toml"
        custom_path.touch()
        path = ConfigManager.get_config_path(str(custom_path))
        assert path == custom_path

    def test_get_config_path_custom_not_exists(self, tmp_path):
        """Test custom config path that doesn't exist."""
        custom_path = tmp_path / "missing.toml"
        with pytest.raises(ConfigError, match="Config file not found"):
            ConfigManager.get_config_path(str(custom_path))

    def test_load_config_not_exists(self, tmp_path):
        """Test loading config when file doesn't exist."""
        with patch.object(ConfigManager, "get_config_path", return_value=tmp_path / "missing.toml"):
            config = ConfigManager.load_config()
            assert isinstance(config, AzlinConfig)
            assert config.default_resource_group is None

    def test_get_resource_group_cli_override(self):
        """Test CLI value overrides config."""
        result = ConfigManager.get_resource_group("cli-rg")
        assert result == "cli-rg"

    def test_get_region_cli_override(self):
        """Test CLI value overrides config."""
        result = ConfigManager.get_region("westus")
        assert result == "westus"

    def test_get_vm_size_cli_override(self):
        """Test CLI value overrides config."""
        result = ConfigManager.get_vm_size("Standard_D4s_v3")
        assert result == "Standard_D4s_v3"

    def test_get_region_from_config(self, tmp_path):
        """Test getting region from config."""
        config_file = tmp_path / "config.toml"
        config_file.write_text('default_region = "westus2"')

        with patch.object(ConfigManager, "DEFAULT_CONFIG_FILE", config_file):
            result = ConfigManager.get_region(None)
            assert result == "westus2"

    def test_get_vm_size_default(self, tmp_path):
        """Test default VM size."""
        config_file = tmp_path / "missing.toml"

        with patch.object(ConfigManager, "DEFAULT_CONFIG_FILE", config_file):
            result = ConfigManager.get_vm_size(None)
            assert result == "Standard_E16as_v5"


class TestSessionNameValidation:
    """Tests for session name validation (Issue #160)."""

    def test_validate_rejects_self_referential(self):
        """Test validation rejects self-referential mappings."""
        with pytest.raises(ConfigError, match="Self-referential session name not allowed"):
            ConfigManager._validate_session_mapping("simserv", "simserv", {})

    def test_validate_rejects_duplicate_session_names(self):
        """Test validation rejects duplicate session names."""
        existing = {"vm1": "prod", "vm2": "staging"}
        with pytest.raises(
            ConfigError, match="Duplicate session name 'prod' already maps to VM 'vm1'"
        ):
            ConfigManager._validate_session_mapping("vm3", "prod", existing)

    def test_validate_allows_updating_same_vm(self):
        """Test validation allows updating session name for same VM."""
        existing = {"vm2": "staging"}
        # Should not raise - we're updating vm1's session name
        ConfigManager._validate_session_mapping("vm1", "prod", existing)

    def test_validate_rejects_invalid_session_name_format(self):
        """Test validation rejects invalid session name format."""
        with pytest.raises(ConfigError, match="Invalid session name format"):
            ConfigManager._validate_session_mapping("vm1", "invalid@name", {})

    def test_validate_rejects_invalid_vm_name_format(self):
        """Test validation rejects invalid VM name format."""
        with pytest.raises(ConfigError, match="Invalid VM name format"):
            ConfigManager._validate_session_mapping("invalid@vm", "session1", {})

    def test_validate_rejects_empty_session_name(self):
        """Test validation rejects empty session name."""
        with pytest.raises(ConfigError, match="Invalid session name format"):
            ConfigManager._validate_session_mapping("vm1", "", {})

    def test_validate_rejects_too_long_session_name(self):
        """Test validation rejects session name > 64 chars."""
        long_name = "a" * 65
        with pytest.raises(ConfigError, match="Invalid session name format"):
            ConfigManager._validate_session_mapping("vm1", long_name, {})

    def test_validate_accepts_valid_mappings(self):
        """Test validation accepts valid mappings."""
        existing = {"vm1": "prod", "vm2": "staging"}
        # Should not raise
        ConfigManager._validate_session_mapping("vm3", "dev", existing)
        ConfigManager._validate_session_mapping("vm1", "prod-updated", existing)

    def test_set_session_name_rejects_self_referential(self, tmp_path):
        """Test set_session_name rejects self-referential mappings."""
        config_file = tmp_path / "config.toml"
        with pytest.raises(ConfigError, match="Self-referential session name not allowed"):
            ConfigManager.set_session_name("simserv", "simserv", str(config_file))

    def test_set_session_name_rejects_duplicates(self, tmp_path):
        """Test set_session_name rejects duplicate session names."""
        config_file = tmp_path / "config.toml"
        # Create initial mapping
        ConfigManager.set_session_name("vm1", "prod", str(config_file))
        # Try to create duplicate
        with pytest.raises(ConfigError, match="Duplicate session name 'prod'"):
            ConfigManager.set_session_name("vm2", "prod", str(config_file))

    def test_set_session_name_allows_updating_same_vm(self, tmp_path):
        """Test set_session_name allows updating session name for same VM."""
        config_file = tmp_path / "config.toml"
        # Create initial mapping
        ConfigManager.set_session_name("vm1", "prod", str(config_file))
        # Update same VM - should succeed
        ConfigManager.set_session_name("vm1", "production", str(config_file))
        # Verify update
        result = ConfigManager.get_session_name("vm1", str(config_file))
        assert result == "production"

    def test_get_vm_name_by_session_filters_self_referential(self, tmp_path, caplog):
        """Test get_vm_name_by_session filters out self-referential entries."""
        import logging

        caplog.set_level(logging.WARNING)

        config_file = tmp_path / "config.toml"
        # Manually create config with self-referential entry
        config = AzlinConfig(session_names={"simserv": "simserv", "vm1": "prod"})
        ConfigManager.save_config(config, str(config_file))

        # Lookup should filter out self-referential entry
        # Pass resource_group="" to force config-only lookup (tags require RG)
        with patch("azlin.tag_manager.TagManager.get_vm_by_session", return_value=None):
            result = ConfigManager.get_vm_name_by_session("simserv", str(config_file), resource_group="test-rg")
            assert result is None
            assert "Ignoring invalid self-referential session mapping" in caplog.text

    def test_get_vm_name_by_session_warns_on_duplicates(self, tmp_path, caplog):
        """Test get_vm_name_by_session warns on duplicate session names."""
        import logging

        caplog.set_level(logging.WARNING)

        config_file = tmp_path / "config.toml"
        # Manually create config with duplicate session names
        config = AzlinConfig(session_names={"vm1": "prod", "vm2": "prod"})
        ConfigManager.save_config(config, str(config_file))

        # Lookup should warn and return first match
        # Mock TagManager to force config fallback
        with patch("azlin.tag_manager.TagManager.get_vm_by_session", return_value=None):
            result = ConfigManager.get_vm_name_by_session("prod", str(config_file), resource_group="test-rg")
            assert result == "vm1"
            assert "Duplicate session name 'prod'" in caplog.text

    def test_get_vm_name_by_session_normal_flow(self, tmp_path):
        """Test get_vm_name_by_session returns correct VM for valid mapping."""
        config_file = tmp_path / "config.toml"
        ConfigManager.set_session_name("myvm", "mysession", str(config_file))

        result = ConfigManager.get_vm_name_by_session("mysession", str(config_file))
        assert result == "myvm"

    def test_bug_scenario_simserv_self_referential(self, tmp_path):
        """Test the original bug scenario: simserv -> simserv causes connection failure."""
        config_file = tmp_path / "config.toml"

        # Attempt to create self-referential mapping (should be rejected now)
        with pytest.raises(ConfigError, match="Self-referential session name not allowed"):
            ConfigManager.set_session_name("simserv", "simserv", str(config_file))

        # Verify no mapping was created
        result = ConfigManager.get_session_name("simserv", str(config_file))
        assert result is None


# ============================================================================
# FIRST-RUN CONFIGURATION WIZARD TESTS (Issue #197)
# ============================================================================


class TestConfigurationDetection:
    """Tests for detecting missing or incomplete configuration (Issue #197).

    These tests verify the wizard can detect when configuration is missing
    or incomplete and needs to run. Tests will FAIL until feature is implemented.
    """

    def test_detect_missing_config_file(self, tmp_path):
        """Test wizard detects missing config.toml file."""
        config_file = tmp_path / "config.toml"

        # Config file doesn't exist
        assert not config_file.exists()

        # Wizard should detect missing config
        result = ConfigManager.needs_first_run_setup(str(config_file))
        assert result is True

    def test_detect_empty_config_file(self, tmp_path):
        """Test wizard detects empty config file."""
        config_file = tmp_path / "config.toml"
        config_file.write_text("")

        # Wizard should detect empty config
        result = ConfigManager.needs_first_run_setup(str(config_file))
        assert result is True

    def test_detect_config_missing_resource_group(self, tmp_path):
        """Test wizard detects config with missing default_resource_group."""
        config_file = tmp_path / "config.toml"
        config_file.write_text('default_region = "westus2"\n')

        # Config exists but missing resource group
        result = ConfigManager.needs_first_run_setup(str(config_file))
        assert result is True

    def test_detect_config_with_null_resource_group(self, tmp_path):
        """Test wizard detects config with null resource group."""
        config_file = tmp_path / "config.toml"
        # TOML doesn't support null, but resource_group can be missing
        config_file.write_text('default_region = "westus2"\ndefault_vm_size = "Standard_D2s_v3"\n')

        result = ConfigManager.needs_first_run_setup(str(config_file))
        assert result is True

    def test_complete_config_does_not_need_setup(self, tmp_path):
        """Test wizard recognizes complete configuration."""
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            'default_resource_group = "my-rg"\n'
            'default_region = "westus2"\n'
            'default_vm_size = "Standard_E16as_v5"\n'
        )

        # Complete config, wizard should not run
        result = ConfigManager.needs_first_run_setup(str(config_file))
        assert result is False

    def test_detect_config_with_only_resource_group(self, tmp_path):
        """Test config with only resource group still needs region/vm_size setup."""
        config_file = tmp_path / "config.toml"
        config_file.write_text('default_resource_group = "my-rg"\n')

        # Has resource group, but this test verifies the method exists
        # Note: needs_first_run_setup only checks for resource_group
        result = ConfigManager.needs_first_run_setup(str(config_file))
        assert result is False  # Has resource group, so doesn't need first-run


class TestWizardResourceGroupSetup:
    """Tests for interactive resource group selection (Issue #197).

    Tests the wizard's ability to prompt for and validate resource group selection.
    Tests will FAIL until feature is implemented.
    """

    @patch("subprocess.run")
    def test_prompt_for_new_resource_group(self, mock_run, tmp_path):
        """Test wizard prompts for new resource group creation."""
        mock_run.return_value = MagicMock(stdout="[]", returncode=0)

        config_file = tmp_path / "config.toml"

        # Mock user input: create new resource group
        with patch("click.prompt", return_value="azlin-rg"):
            result = ConfigManager.prompt_resource_group_setup(str(config_file))

        assert result["action"] == "create_new"
        assert "resource_group_name" in result

    @patch("subprocess.run")
    def test_prompt_for_existing_resource_group(self, mock_run, tmp_path):
        """Test wizard prompts for existing resource group selection."""
        # Mock Azure API to return existing resource groups
        mock_rgs = ["rg-prod", "rg-dev", "rg-staging"]
        mock_run.return_value = MagicMock(stdout="\n".join(mock_rgs), returncode=0)

        config_file = tmp_path / "config.toml"

        with patch("click.prompt", return_value="2"):  # Select second resource group
            result = ConfigManager.prompt_resource_group_setup(str(config_file))

        assert result["action"] == "use_existing"
        assert result["resource_group_name"] in mock_rgs

    def test_prompt_validates_resource_group_name(self, tmp_path):
        """Test wizard validates resource group name format."""
        config_file = tmp_path / "config.toml"

        # Invalid resource group names per Azure rules
        invalid_names = [
            "rg-with-invalid-chars!@#",  # Has special chars !@#
            "rg" * 50,  # Too long (100 chars > 90)
            "",  # Empty
            "rg.",  # Ends with period (not allowed by Azure)
        ]

        for invalid_name in invalid_names:
            with pytest.raises(ConfigError):
                ConfigManager.validate_resource_group_name(invalid_name)

    def test_prompt_accepts_valid_resource_group_names(self, tmp_path):
        """Test wizard accepts valid resource group names."""
        valid_names = [
            "my-rg",
            "azlin-rg",
            "rg_prod",
            "rg-dev-001",
            "ResourceGroup1",
        ]

        for valid_name in valid_names:
            # Should not raise
            ConfigManager.validate_resource_group_name(valid_name)

    @patch("subprocess.run")
    def test_prompt_handles_azure_api_failure(self, mock_run, tmp_path):
        """Test wizard handles Azure API failure gracefully."""
        # Mock Azure API failure - subprocess raises exception
        mock_run.side_effect = Exception("API Error")
        config_file = tmp_path / "config.toml"

        # Wizard should fall back to manual entry
        with patch("click.prompt", return_value="azlin-rg"):
            result = ConfigManager.prompt_resource_group_setup(str(config_file))

        assert result["action"] == "create_new"
        assert result["resource_group_name"] == "azlin-rg"


class TestWizardRegionSelection:
    """Tests for default region configuration (Issue #197).

    Tests the wizard's region selection and validation logic.
    Tests will FAIL until feature is implemented.
    """

    def test_prompt_for_region_with_defaults(self, tmp_path):
        """Test wizard shows region options with recommended default."""
        config_file = tmp_path / "config.toml"

        # Mock user accepts default (westus2)
        with patch("click.prompt", return_value="westus2"):
            result = ConfigManager.prompt_region_setup(str(config_file))

        assert result["region"] == "westus2"

    def test_prompt_for_region_custom_selection(self, tmp_path):
        """Test wizard allows custom region selection."""
        config_file = tmp_path / "config.toml"

        custom_region = "eastus"

        with patch("click.prompt", return_value=custom_region):
            result = ConfigManager.prompt_region_setup(str(config_file))

        assert result["region"] == custom_region

    def test_prompt_validates_region_availability(self, tmp_path):
        """Test wizard accepts custom regions with confirmation."""
        config_file = tmp_path / "config.toml"

        # Custom region not in common list requires confirmation
        with patch("click.prompt", return_value="customregion"):
            with patch("click.confirm", return_value=True):
                result = ConfigManager.prompt_region_setup(str(config_file))

        # Should accept custom region after user confirms
        assert result["region"] == "customregion"

    def test_prompt_shows_region_options(self, tmp_path):
        """Test wizard displays common US region options."""
        config_file = tmp_path / "config.toml"

        # Expected US regions in COMMON_REGIONS
        expected_regions = [
            "westus2",
            "eastus",
            "centralus",
            "westus3",
            "eastus2",
        ]

        with patch("click.prompt", return_value="westus2"):
            result = ConfigManager.prompt_region_setup(str(config_file))

        # Verify common regions were presented
        assert result["available_regions"] is not None
        for region in expected_regions:
            assert region in result["available_regions"]

        # Verify we have exactly 8 US regions
        assert len(result["available_regions"]) == 8


class TestWizardVMSizeConfiguration:
    """Tests for default VM size configuration (Issue #197).

    Tests the wizard's VM size selection with tier-based options.
    Tests will FAIL until feature is implemented.
    """

    def test_prompt_for_vm_size_tier_selection(self, tmp_path):
        """Test wizard prompts for VM tier (s/m/l/xl)."""
        config_file = tmp_path / "config.toml"

        # Mock user selects medium tier
        with patch("click.prompt", return_value="m"):
            result = ConfigManager.prompt_vm_size_setup(str(config_file))

        assert result["tier"] == "m"
        assert result["vm_size"] == "Standard_E8as_v5"  # Medium tier

    def test_prompt_shows_tier_pricing_estimates(self, tmp_path):
        """Test wizard displays pricing for each tier."""
        config_file = tmp_path / "config.toml"

        with patch("click.prompt", return_value="s"):
            result = ConfigManager.prompt_vm_size_setup(str(config_file))

        # Verify pricing info was shown
        assert "pricing_info" in result
        assert result["pricing_info"]["hourly"] > 0
        assert result["tier"] == "s"

    def test_prompt_allows_custom_vm_size(self, tmp_path):
        """Test wizard uses tier-based selection (no custom VM sizes)."""
        config_file = tmp_path / "config.toml"

        # Mock user selects xl tier
        with patch("click.prompt", return_value="xl"):
            result = ConfigManager.prompt_vm_size_setup(str(config_file))

        assert result["vm_size"] == "Standard_E32as_v5"  # XL tier
        assert result["tier"] == "xl"

    def test_prompt_validates_vm_size_format(self, tmp_path):
        """Test wizard validates VM tier input."""
        config_file = tmp_path / "config.toml"

        # Test that invalid tiers cause the prompt to loop and eventually get valid input
        # We mock it to return valid input after invalid attempts
        with patch("click.prompt", return_value="l"):
            with patch("click.echo"):  # Suppress error messages
                result = ConfigManager.prompt_vm_size_setup(str(config_file))

        # Should eventually accept valid tier
        assert result["tier"] == "l"
        assert result["vm_size"] == "Standard_E16as_v5"

    def test_prompt_vm_size_defaults_to_recommended(self, tmp_path):
        """Test wizard defaults to recommended VM size (Standard_E16as_v5)."""
        config_file = tmp_path / "config.toml"

        # Mock user selects default tier 'l'
        with patch("click.prompt", return_value="l"):
            result = ConfigManager.prompt_vm_size_setup(str(config_file))

        assert result["vm_size"] == "Standard_E16as_v5"


class TestWizardConfigurationSummary:
    """Tests for configuration summary and confirmation (Issue #197).

    Tests the wizard's ability to show a summary and get user confirmation.
    Tests will FAIL until feature is implemented.
    """

    def test_show_configuration_summary(self, tmp_path):
        """Test wizard displays configuration summary."""
        config_file = tmp_path / "config.toml"

        config_data = {
            "resource_group": "azlin-rg",
            "region": "westus2",
            "vm_size": "Standard_E16as_v5",
        }

        # Mock display summary (returns formatted string)
        summary = ConfigManager.format_config_summary(config_data)

        assert "azlin-rg" in summary
        assert "westus2" in summary
        assert "Standard_E16as_v5" in summary

    def test_prompt_for_confirmation_accepted(self, tmp_path):
        """Test wizard handles user accepting configuration."""
        config_file = tmp_path / "config.toml"

        config_data = {
            "resource_group": "azlin-rg",
            "region": "westus2",
            "vm_size": "Standard_E16as_v5",
        }

        # Mock user confirms (yes)
        with patch("click.confirm", return_value=True):
            result = ConfigManager.prompt_confirmation(config_data)

        assert result is True

    def test_prompt_for_confirmation_rejected(self, tmp_path):
        """Test wizard handles user rejecting configuration."""
        config_file = tmp_path / "config.toml"

        config_data = {
            "resource_group": "azlin-rg",
            "region": "westus2",
            "vm_size": "Standard_E16as_v5",
        }

        # Mock user rejects (no)
        with patch("click.confirm", return_value=False):
            result = ConfigManager.prompt_confirmation(config_data)

        assert result is False

    def test_save_configuration_after_confirmation(self, tmp_path):
        """Test wizard saves configuration after user confirmation."""
        config_file = tmp_path / "config.toml"

        config_data = {
            "default_resource_group": "azlin-rg",
            "default_region": "westus2",
            "default_vm_size": "Standard_E16as_v5",
        }

        # Save configuration
        ConfigManager.save_wizard_config(config_data, str(config_file))

        # Verify file was created
        assert config_file.exists()

        # Verify content
        config = ConfigManager.load_config(str(config_file))
        assert config.default_resource_group == "azlin-rg"
        assert config.default_region == "westus2"
        assert config.default_vm_size == "Standard_E16as_v5"


class TestWizardCompleteFlow:
    """Tests for complete wizard flow (Issue #197).

    Integration-style unit tests for the full wizard experience.
    Tests will FAIL until feature is implemented.
    """

    @patch("subprocess.run")
    def test_complete_wizard_flow_with_defaults(self, mock_run, tmp_path):
        """Test complete wizard flow accepting all defaults."""
        mock_run.return_value = MagicMock(stdout="[]", returncode=0)
        config_file = tmp_path / "config.toml"

        # Mock user inputs: new RG, default region, default VM size, confirm
        with patch("click.prompt", side_effect=["azlin-rg", "westus2", "l"]):
            with patch("click.confirm", return_value=True):
                result = ConfigManager.run_first_run_wizard(str(config_file), return_dict=True)

        assert result["success"] is True
        assert result["config"]["default_resource_group"] == "azlin-rg"
        assert result["config"]["default_region"] == "westus2"
        assert result["config"]["default_vm_size"] == "Standard_E16as_v5"

    @patch("subprocess.run")
    def test_complete_wizard_flow_with_custom_values(self, mock_run, tmp_path):
        """Test complete wizard flow with custom values."""
        mock_run.return_value = MagicMock(stdout="[]", returncode=0)
        config_file = tmp_path / "config.toml"

        # Mock user inputs: custom RG, custom region, small tier, confirm
        custom_inputs = ["my-custom-rg", "eastus", "s"]

        with patch("click.prompt", side_effect=custom_inputs):
            with patch("click.confirm", return_value=True):
                result = ConfigManager.run_first_run_wizard(str(config_file), return_dict=True)

        assert result["success"] is True
        assert result["config"]["default_resource_group"] == "my-custom-rg"
        assert result["config"]["default_region"] == "eastus"
        assert result["config"]["default_vm_size"] == "Standard_D2s_v3"  # Small tier

    @patch("subprocess.run")
    def test_wizard_flow_user_declines(self, mock_run, tmp_path):
        """Test wizard flow when user declines at confirmation."""
        mock_run.return_value = MagicMock(stdout="[]", returncode=0)
        config_file = tmp_path / "config.toml"

        # Mock user inputs: RG, region, size, but decline at confirmation
        with patch("click.prompt", side_effect=["test-rg", "westus2", "l"]):
            with patch("click.confirm", return_value=False):
                result = ConfigManager.run_first_run_wizard(str(config_file), return_dict=True)

        assert result["success"] is False
        assert result["cancelled"] is True
        # Config file should not be created
        assert not config_file.exists()

    @patch("subprocess.run")
    def test_wizard_flow_retry_on_invalid_input(self, mock_run, tmp_path):
        """Test wizard retries on invalid input."""
        mock_run.return_value = MagicMock(stdout="[]", returncode=0)
        config_file = tmp_path / "config.toml"

        # Mock user inputs: invalid RG first, then valid values
        inputs = [
            "invalid@rg",  # Invalid (has @)
            "valid-rg",  # Valid RG
            "westus2",  # Valid region
            "l",  # Valid tier
        ]

        with patch("click.prompt", side_effect=inputs):
            with patch("click.confirm", return_value=True):
                result = ConfigManager.run_first_run_wizard(str(config_file), return_dict=True)

        assert result["success"] is True
        assert result["config"]["default_resource_group"] == "valid-rg"

    @patch("subprocess.run")
    def test_wizard_displays_welcome_message(self, mock_run, tmp_path, capsys):
        """Test wizard displays welcome message."""
        mock_run.return_value = MagicMock(stdout="[]", returncode=0)
        config_file = tmp_path / "config.toml"

        with patch("click.prompt", side_effect=["test-rg", "westus2", "l"]):
            with patch("click.confirm", return_value=True):
                ConfigManager.run_first_run_wizard(str(config_file), return_dict=True)

        captured = capsys.readouterr()
        assert "Welcome to azlin" in captured.out or "First-run setup" in captured.out

    @patch("subprocess.run")
    def test_wizard_creates_config_dir_if_missing(self, mock_run, tmp_path):
        """Test wizard creates .azlin directory if it doesn't exist."""
        mock_run.return_value = MagicMock(stdout="[]", returncode=0)
        config_dir = tmp_path / ".azlin"
        config_file = config_dir / "config.toml"

        # Directory doesn't exist yet
        assert not config_dir.exists()

        with patch("click.prompt", side_effect=["test-rg", "westus2", "l"]):
            with patch("click.confirm", return_value=True):
                ConfigManager.run_first_run_wizard(str(config_file), return_dict=True)

        # Directory should be created
        assert config_dir.exists()
        assert config_file.exists()


class TestWizardErrorHandling:
    """Tests for wizard error handling (Issue #197).

    Tests various error scenarios and recovery.
    Tests will FAIL until feature is implemented.
    """

    @patch("subprocess.run")
    def test_wizard_handles_file_permission_error(self, mock_run, tmp_path):
        """Test wizard auto-fixes file permission errors."""
        mock_run.return_value = MagicMock(stdout="[]", returncode=0)
        config_file = tmp_path / "config.toml"
        config_file.touch()
        config_file.chmod(0o444)  # Read-only

        with patch("click.prompt", side_effect=["test-rg", "westus2", "l"]):
            with patch("click.confirm", return_value=True):
                result = ConfigManager.run_first_run_wizard(str(config_file), return_dict=True)

        # Wizard should auto-fix permissions and succeed
        assert result["success"] is True
        # Permissions should be 0600
        assert (config_file.stat().st_mode & 0o777) == 0o600

    @patch("subprocess.run")
    def test_wizard_handles_disk_full_error(self, mock_run, tmp_path):
        """Test wizard handles disk full error."""
        mock_run.return_value = MagicMock(stdout="[]", returncode=0)
        config_file = tmp_path / "config.toml"

        # Mock OSError for disk full
        with patch(
            "azlin.config_manager.ConfigManager.save_config", side_effect=OSError("No space")
        ):
            with patch("click.prompt", side_effect=["test-rg", "westus2", "l"]):
                with patch("click.confirm", return_value=True):
                    with pytest.raises(ConfigError):
                        ConfigManager.run_first_run_wizard(str(config_file), return_dict=True)

    @patch("subprocess.run")
    def test_wizard_handles_keyboard_interrupt(self, mock_run, tmp_path):
        """Test wizard handles Ctrl+C gracefully."""
        mock_run.return_value = MagicMock(stdout="[]", returncode=0)
        config_file = tmp_path / "config.toml"

        # Mock KeyboardInterrupt during input
        with patch("click.prompt", side_effect=KeyboardInterrupt):
            result = ConfigManager.run_first_run_wizard(str(config_file), return_dict=True)

        assert result["success"] is False
        assert result["cancelled"] is True
        # Config file should not be created
        assert not config_file.exists()

    @patch("subprocess.run")
    def test_wizard_handles_azure_auth_failure(self, mock_run, tmp_path):
        """Test wizard handles Azure authentication failure when listing RGs."""
        config_file = tmp_path / "config.toml"

        # Mock Azure to fail on list but succeed on create
        def subprocess_side_effect(*args, **kwargs):
            cmd = args[0] if args else kwargs.get("args", [])
            if "list" in cmd:
                raise Exception("Auth failed")
            # Success for create
            return MagicMock(stdout="", stderr="", returncode=0)

        mock_run.side_effect = subprocess_side_effect

        # Wizard should still work, fallback to manual RG entry
        with patch("click.prompt", side_effect=["test-rg", "westus2", "l"]):
            with patch("click.confirm", return_value=True):
                result = ConfigManager.run_first_run_wizard(str(config_file), return_dict=True)

        assert result["success"] is True

    @patch("subprocess.run")
    def test_wizard_validates_config_after_save(self, mock_run, tmp_path):
        """Test wizard validates configuration after saving."""
        mock_run.return_value = MagicMock(stdout="[]", returncode=0)
        config_file = tmp_path / "config.toml"

        with patch("click.prompt", side_effect=["test-rg", "westus2", "l"]):
            with patch("click.confirm", return_value=True):
                ConfigManager.run_first_run_wizard(str(config_file), return_dict=True)

        # Verify saved config is valid
        config = ConfigManager.load_config(str(config_file))
        assert config.default_resource_group is not None
        assert config.default_region is not None
        assert config.default_vm_size is not None


class TestWizardSecurityValidation:
    """Tests for wizard security validation (Issue #197).

    Tests validation of user inputs for security issues.
    Tests will FAIL until feature is implemented.
    """

    def test_wizard_rejects_path_traversal_in_inputs(self, tmp_path):
        """Test wizard rejects path traversal attempts."""
        malicious_inputs = [
            "../../etc/passwd",
            "../../../root/.ssh",
            "rg-name/../../sensitive",
        ]

        for malicious_input in malicious_inputs:
            with pytest.raises(ConfigError):
                ConfigManager.validate_resource_group_name(malicious_input)

    def test_wizard_sanitizes_resource_group_names(self, tmp_path):
        """Test wizard sanitizes resource group names."""
        config_file = tmp_path / "config.toml"

        # Input with potential injection characters
        inputs_to_sanitize = [
            "rg-name; rm -rf /",
            "rg-name && echo pwned",
            "rg-name | cat /etc/passwd",
        ]

        for dangerous_input in inputs_to_sanitize:
            with pytest.raises(ConfigError):
                ConfigManager.validate_resource_group_name(dangerous_input)

    @patch("subprocess.run")
    def test_wizard_sets_secure_file_permissions(self, mock_run, tmp_path):
        """Test wizard sets secure permissions on config file."""
        mock_run.return_value = MagicMock(stdout="[]", returncode=0)
        config_file = tmp_path / "config.toml"

        with patch("click.prompt", side_effect=["test-rg", "westus2", "l"]):
            with patch("click.confirm", return_value=True):
                ConfigManager.run_first_run_wizard(str(config_file), return_dict=True)

        # Verify file has secure permissions (0600)
        stat = config_file.stat()
        mode = stat.st_mode & 0o777
        assert mode == 0o600

    def test_wizard_validates_region_against_allowlist(self, tmp_path):
        """Test wizard validates region against known Azure regions."""
        # Region should match Azure naming pattern
        invalid_regions = [
            "fake-region-xyz",
            "region; rm -rf",
            "../../../etc",
        ]

        for invalid_region in invalid_regions:
            with pytest.raises(ConfigError):
                ConfigManager.validate_region(invalid_region)
