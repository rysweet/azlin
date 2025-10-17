"""
Unit tests for TemplateManager module.

Tests template creation, listing, deletion, export, and import functionality.
Tests YAML serialization and validation.

Test Coverage (TDD - RED phase):
- Template creation
- Template listing
- Template retrieval
- Template deletion
- Template export/import
- YAML serialization/deserialization
- Input validation
- Error handling
"""

from unittest.mock import patch

import pytest

# ============================================================================
# TEMPLATE CREATION TESTS
# ============================================================================


class TestTemplateCreation:
    """Test template creation functionality."""

    def test_create_template_with_all_fields(self, tmp_path):
        """Test creating a template with all fields populated.

        RED PHASE: This test will fail - no implementation yet.
        """
        from azlin.template_manager import TemplateManager, VMTemplateConfig

        template = VMTemplateConfig(
            name="dev-vm",
            description="Development VM with standard tools",
            vm_size="Standard_D2s_v3",
            region="eastus",
            cloud_init="#cloud-config\npackages:\n  - docker",
            custom_metadata={"created_by": "test@example.com"},
        )

        # Override templates directory
        with patch.object(TemplateManager, "TEMPLATES_DIR", tmp_path):
            TemplateManager.create_template(template)

            # Verify file was created
            template_file = tmp_path / "dev-vm.yaml"
            assert template_file.exists()

    def test_create_template_with_minimal_fields(self, tmp_path):
        """Test creating a template with only required fields."""
        from azlin.template_manager import TemplateManager, VMTemplateConfig

        template = VMTemplateConfig(
            name="minimal-vm",
            description="Minimal template",
            vm_size="Standard_B2s",
            region="westus2",
        )

        with patch.object(TemplateManager, "TEMPLATES_DIR", tmp_path):
            TemplateManager.create_template(template)

            template_file = tmp_path / "minimal-vm.yaml"
            assert template_file.exists()

    def test_create_template_invalid_name_fails(self, tmp_path):
        """Test that invalid template names are rejected."""
        from azlin.template_manager import TemplateError, TemplateManager, VMTemplateConfig

        # Test path traversal attempt
        template = VMTemplateConfig(
            name="../../../etc/passwd",
            description="Malicious template",
            vm_size="Standard_B2s",
            region="eastus",
        )

        with patch.object(TemplateManager, "TEMPLATES_DIR", tmp_path):
            with pytest.raises(TemplateError, match="Invalid template name"):
                TemplateManager.create_template(template)

    def test_create_template_duplicate_name_fails(self, tmp_path):
        """Test that creating a template with duplicate name fails."""
        from azlin.template_manager import TemplateError, TemplateManager, VMTemplateConfig

        template = VMTemplateConfig(
            name="duplicate", description="First template", vm_size="Standard_B2s", region="eastus"
        )

        with patch.object(TemplateManager, "TEMPLATES_DIR", tmp_path):
            TemplateManager.create_template(template)

            # Try to create again with same name
            with pytest.raises(TemplateError, match="already exists"):
                TemplateManager.create_template(template)

    def test_create_template_creates_directory(self, tmp_path):
        """Test that template directory is created if it doesn't exist."""
        from azlin.template_manager import TemplateManager, VMTemplateConfig

        templates_dir = tmp_path / "templates"
        assert not templates_dir.exists()

        template = VMTemplateConfig(
            name="test", description="Test", vm_size="Standard_B2s", region="eastus"
        )

        with patch.object(TemplateManager, "TEMPLATES_DIR", templates_dir):
            TemplateManager.create_template(template)

            assert templates_dir.exists()
            assert templates_dir.is_dir()


# ============================================================================
# TEMPLATE LISTING TESTS
# ============================================================================


class TestTemplateListing:
    """Test template listing functionality."""

    def test_list_templates_empty_directory(self, tmp_path):
        """Test listing templates when directory is empty."""
        from azlin.template_manager import TemplateManager

        with patch.object(TemplateManager, "TEMPLATES_DIR", tmp_path):
            templates = TemplateManager.list_templates()

            assert isinstance(templates, list)
            assert len(templates) == 0

    def test_list_templates_multiple_templates(self, tmp_path):
        """Test listing multiple templates."""
        from azlin.template_manager import TemplateManager, VMTemplateConfig

        # Create multiple templates
        template1 = VMTemplateConfig(
            name="template1", description="First template", vm_size="Standard_B2s", region="eastus"
        )
        template2 = VMTemplateConfig(
            name="template2",
            description="Second template",
            vm_size="Standard_D2s_v3",
            region="westus2",
        )

        with patch.object(TemplateManager, "TEMPLATES_DIR", tmp_path):
            TemplateManager.create_template(template1)
            TemplateManager.create_template(template2)

            templates = TemplateManager.list_templates()

            assert len(templates) == 2
            assert any(t.name == "template1" for t in templates)
            assert any(t.name == "template2" for t in templates)

    def test_list_templates_sorted_alphabetically(self, tmp_path):
        """Test that templates are sorted alphabetically."""
        from azlin.template_manager import TemplateManager, VMTemplateConfig

        # Create templates in reverse alphabetical order
        for name in ["zebra", "alpha", "middle"]:
            template = VMTemplateConfig(
                name=name, description=f"{name} template", vm_size="Standard_B2s", region="eastus"
            )
            with patch.object(TemplateManager, "TEMPLATES_DIR", tmp_path):
                TemplateManager.create_template(template)

        with patch.object(TemplateManager, "TEMPLATES_DIR", tmp_path):
            templates = TemplateManager.list_templates()

            names = [t.name for t in templates]
            assert names == ["alpha", "middle", "zebra"]


# ============================================================================
# TEMPLATE RETRIEVAL TESTS
# ============================================================================


class TestTemplateRetrieval:
    """Test template retrieval functionality."""

    def test_get_existing_template(self, tmp_path):
        """Test retrieving an existing template."""
        from azlin.template_manager import TemplateManager, VMTemplateConfig

        original = VMTemplateConfig(
            name="test-vm",
            description="Test template",
            vm_size="Standard_D2s_v3",
            region="eastus",
            cloud_init="#cloud-config",
        )

        with patch.object(TemplateManager, "TEMPLATES_DIR", tmp_path):
            TemplateManager.create_template(original)

            retrieved = TemplateManager.get_template("test-vm")

            assert retrieved.name == "test-vm"
            assert retrieved.description == "Test template"
            assert retrieved.vm_size == "Standard_D2s_v3"
            assert retrieved.region == "eastus"
            assert retrieved.cloud_init == "#cloud-config"

    def test_get_nonexistent_template_fails(self, tmp_path):
        """Test that retrieving non-existent template raises error."""
        from azlin.template_manager import TemplateError, TemplateManager

        with patch.object(TemplateManager, "TEMPLATES_DIR", tmp_path):
            with pytest.raises(TemplateError, match="not found"):
                TemplateManager.get_template("nonexistent")


# ============================================================================
# TEMPLATE DELETION TESTS
# ============================================================================


class TestTemplateDeletion:
    """Test template deletion functionality."""

    def test_delete_existing_template(self, tmp_path):
        """Test deleting an existing template."""
        from azlin.template_manager import TemplateManager, VMTemplateConfig

        template = VMTemplateConfig(
            name="to-delete", description="Will be deleted", vm_size="Standard_B2s", region="eastus"
        )

        with patch.object(TemplateManager, "TEMPLATES_DIR", tmp_path):
            TemplateManager.create_template(template)

            template_file = tmp_path / "to-delete.yaml"
            assert template_file.exists()

            TemplateManager.delete_template("to-delete")

            assert not template_file.exists()

    def test_delete_nonexistent_template_fails(self, tmp_path):
        """Test that deleting non-existent template raises error."""
        from azlin.template_manager import TemplateError, TemplateManager

        with patch.object(TemplateManager, "TEMPLATES_DIR", tmp_path):
            with pytest.raises(TemplateError, match="not found"):
                TemplateManager.delete_template("nonexistent")


# ============================================================================
# TEMPLATE EXPORT/IMPORT TESTS
# ============================================================================


class TestTemplateExportImport:
    """Test template export and import functionality."""

    def test_export_template_to_file(self, tmp_path):
        """Test exporting a template to a YAML file."""
        from azlin.template_manager import TemplateManager, VMTemplateConfig

        template = VMTemplateConfig(
            name="export-test",
            description="Template for export",
            vm_size="Standard_D2s_v3",
            region="eastus",
        )

        templates_dir = tmp_path / "templates"
        output_file = tmp_path / "exported.yaml"

        with patch.object(TemplateManager, "TEMPLATES_DIR", templates_dir):
            TemplateManager.create_template(template)
            TemplateManager.export_template("export-test", output_file)

            assert output_file.exists()

    def test_import_template_from_file(self, tmp_path):
        """Test importing a template from a YAML file."""
        from azlin.template_manager import TemplateManager

        # Create a template file manually
        yaml_content = """name: imported-vm
description: Imported template
vm_size: Standard_D2s_v3
region: westus2
cloud_init: |
  #cloud-config
  packages:
    - docker
"""
        input_file = tmp_path / "import.yaml"
        input_file.write_text(yaml_content)

        templates_dir = tmp_path / "templates"

        with patch.object(TemplateManager, "TEMPLATES_DIR", templates_dir):
            imported = TemplateManager.import_template(input_file)

            assert imported.name == "imported-vm"
            assert imported.description == "Imported template"
            assert imported.vm_size == "Standard_D2s_v3"
            assert imported.region == "westus2"

            # Verify it was saved
            assert (templates_dir / "imported-vm.yaml").exists()

    def test_import_invalid_yaml_fails(self, tmp_path):
        """Test that importing invalid YAML raises error."""
        from azlin.template_manager import TemplateError, TemplateManager

        input_file = tmp_path / "invalid.yaml"
        input_file.write_text("{ invalid yaml content [")

        with patch.object(TemplateManager, "TEMPLATES_DIR", tmp_path / "templates"):
            with pytest.raises(TemplateError, match="Invalid YAML"):
                TemplateManager.import_template(input_file)

    def test_import_missing_required_fields_fails(self, tmp_path):
        """Test that importing template with missing fields fails."""
        from azlin.template_manager import TemplateError, TemplateManager

        yaml_content = """name: incomplete
# Missing description, vm_size, region
"""
        input_file = tmp_path / "incomplete.yaml"
        input_file.write_text(yaml_content)

        with patch.object(TemplateManager, "TEMPLATES_DIR", tmp_path / "templates"):
            with pytest.raises(TemplateError, match="Missing required field"):
                TemplateManager.import_template(input_file)


# ============================================================================
# YAML SERIALIZATION TESTS
# ============================================================================


class TestYAMLSerialization:
    """Test YAML serialization and deserialization."""

    def test_template_to_yaml_dict(self):
        """Test converting template to YAML-compatible dict."""
        from azlin.template_manager import VMTemplateConfig

        template = VMTemplateConfig(
            name="test",
            description="Test template",
            vm_size="Standard_B2s",
            region="eastus",
            cloud_init="#cloud-config",
            custom_metadata={"key": "value"},
        )

        yaml_dict = template.to_dict()

        assert yaml_dict["name"] == "test"
        assert yaml_dict["description"] == "Test template"
        assert yaml_dict["vm_size"] == "Standard_B2s"
        assert yaml_dict["region"] == "eastus"
        assert yaml_dict["cloud_init"] == "#cloud-config"
        assert yaml_dict["custom_metadata"] == {"key": "value"}

    def test_template_from_yaml_dict(self):
        """Test creating template from YAML dict."""
        from azlin.template_manager import VMTemplateConfig

        yaml_dict = {
            "name": "from-dict",
            "description": "Created from dict",
            "vm_size": "Standard_D2s_v3",
            "region": "westus2",
            "cloud_init": "#cloud-config\npackages:\n  - git",
            "custom_metadata": {"author": "test"},
        }

        template = VMTemplateConfig.from_dict(yaml_dict)

        assert template.name == "from-dict"
        assert template.description == "Created from dict"
        assert template.vm_size == "Standard_D2s_v3"
        assert template.region == "westus2"
        assert template.cloud_init == "#cloud-config\npackages:\n  - git"
        assert template.custom_metadata == {"author": "test"}


# ============================================================================
# VALIDATION TESTS
# ============================================================================


class TestTemplateValidation:
    """Test template validation logic."""

    def test_validate_template_name_alphanumeric(self):
        """Test that template names must be alphanumeric with hyphens."""
        from azlin.template_manager import TemplateManager

        # Valid names
        assert TemplateManager.validate_template_name("dev-vm") is True
        assert TemplateManager.validate_template_name("test123") is True
        assert TemplateManager.validate_template_name("my-dev-vm-01") is True

        # Invalid names
        assert TemplateManager.validate_template_name("../etc/passwd") is False
        assert TemplateManager.validate_template_name("test/vm") is False
        assert TemplateManager.validate_template_name("test vm") is False
        assert TemplateManager.validate_template_name("test@vm") is False

    def test_validate_template_fields(self):
        """Test validation of required template fields."""
        from azlin.template_manager import TemplateError, VMTemplateConfig

        # Valid template
        valid = VMTemplateConfig(
            name="valid", description="Valid template", vm_size="Standard_B2s", region="eastus"
        )
        valid.validate()  # Should not raise

        # Invalid - empty name
        with pytest.raises(TemplateError):
            invalid = VMTemplateConfig(
                name="", description="Invalid", vm_size="Standard_B2s", region="eastus"
            )
            invalid.validate()

        # Invalid - empty description
        with pytest.raises(TemplateError):
            invalid = VMTemplateConfig(
                name="test", description="", vm_size="Standard_B2s", region="eastus"
            )
            invalid.validate()


# ============================================================================
# EDGE CASES
# ============================================================================


class TestTemplateEdgeCases:
    """Test edge cases and error handling."""

    def test_template_with_long_name(self, tmp_path):
        """Test template with very long name."""
        from azlin.template_manager import TemplateError, TemplateManager, VMTemplateConfig

        long_name = "a" * 256  # Very long name

        template = VMTemplateConfig(
            name=long_name, description="Long name test", vm_size="Standard_B2s", region="eastus"
        )

        with patch.object(TemplateManager, "TEMPLATES_DIR", tmp_path):
            with pytest.raises(TemplateError, match="(too long|Invalid template name)"):
                TemplateManager.create_template(template)

    def test_template_with_special_characters(self, tmp_path):
        """Test template with special characters in name."""
        from azlin.template_manager import TemplateError, TemplateManager, VMTemplateConfig

        template = VMTemplateConfig(
            name="test!@#$%", description="Special chars", vm_size="Standard_B2s", region="eastus"
        )

        with patch.object(TemplateManager, "TEMPLATES_DIR", tmp_path):
            with pytest.raises(TemplateError, match="Invalid template name"):
                TemplateManager.create_template(template)

    def test_corrupted_yaml_file_handling(self, tmp_path):
        """Test handling of corrupted YAML files during listing."""
        from azlin.template_manager import TemplateManager, VMTemplateConfig

        # Create a valid template
        template = VMTemplateConfig(
            name="valid", description="Valid template", vm_size="Standard_B2s", region="eastus"
        )

        with patch.object(TemplateManager, "TEMPLATES_DIR", tmp_path):
            TemplateManager.create_template(template)

            # Corrupt the YAML file
            corrupted_file = tmp_path / "corrupted.yaml"
            corrupted_file.write_text("{ invalid yaml [")

            # list_templates should skip corrupted files
            templates = TemplateManager.list_templates()
            assert len(templates) == 1  # Only the valid one
            assert templates[0].name == "valid"
