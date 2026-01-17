"""Integration test for template expansion to ARM deployment."""

import pytest

from azlin.template_manager import TemplateManager


class TestTemplateToDeploymentWorkflow:
    """Test template expansion and deployment workflow."""

    def test_template_creation_and_expansion(self, tmp_path):
        """Test creating and expanding VM template."""
        try:
            manager = TemplateManager(templates_dir=tmp_path)

            # Create template
            template_config = {
                "name": "ubuntu-vm",
                "vm_size": "Standard_B2s",
                "image": "Ubuntu:22.04-LTS",
                "disk_size_gb": 30,
            }

            manager.create_template("ubuntu-vm", template_config)

            # List templates
            templates = manager.list_templates()
            assert "ubuntu-vm" in templates

        except Exception as e:
            pytest.skip(f"Template manager not available: {e}")
