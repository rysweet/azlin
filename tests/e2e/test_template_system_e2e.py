"""End-to-end tests for template system V2.

Test coverage: Complete template system lifecycle from CLI to execution.

These tests follow TDD - they should FAIL initially until implementation is complete.
"""

import json
import subprocess
import tempfile
from pathlib import Path


class TestTemplateSystemE2E:
    """End-to-end tests for complete template system."""

    def test_cli_create_template(self):
        """Test creating template via CLI."""
        with tempfile.TemporaryDirectory() as tmpdir:
            result = subprocess.run(
                [
                    "azlin",
                    "template",
                    "create",
                    "--name",
                    "e2e-vm",
                    "--version",
                    "1.0.0",
                    "--description",
                    "E2E test template",
                    "--author",
                    "e2e-test",
                    "--output",
                    str(Path(tmpdir) / "template.json"),
                ],
                capture_output=True,
                text=True,
            )

            assert result.returncode == 0
            assert Path(tmpdir) / "template.json" in Path(tmpdir).iterdir()

            # Verify template content
            template_data = json.loads((Path(tmpdir) / "template.json").read_text())
            assert template_data["metadata"]["name"] == "e2e-vm"
            assert template_data["metadata"]["version"] == "1.0.0"

    def test_cli_validate_template(self):
        """Test validating template via CLI."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a template file
            template_path = Path(tmpdir) / "template.json"
            template_data = {
                "metadata": {
                    "name": "test-template",
                    "version": "1.0.0",
                    "description": "Test",
                    "author": "test",
                },
                "content": {"resources": []},
            }
            template_path.write_text(json.dumps(template_data))

            # Validate
            result = subprocess.run(
                ["azlin", "template", "validate", str(template_path)],
                capture_output=True,
                text=True,
            )

            assert result.returncode == 0
            assert "valid" in result.stdout.lower()

    def test_cli_publish_template(self):
        """Test publishing template to marketplace via CLI."""
        with tempfile.TemporaryDirectory() as tmpdir:
            template_path = Path(tmpdir) / "template.json"
            template_data = {
                "metadata": {
                    "name": "published-template",
                    "version": "1.0.0",
                    "description": "Published template",
                    "author": "publisher",
                },
                "content": {},
            }
            template_path.write_text(json.dumps(template_data))

            result = subprocess.run(
                ["azlin", "template", "publish", str(template_path)], capture_output=True, text=True
            )

            assert result.returncode == 0
            assert "published" in result.stdout.lower()

    def test_cli_search_templates(self):
        """Test searching templates in marketplace via CLI."""
        result = subprocess.run(
            ["azlin", "template", "search", "--tag", "compute"], capture_output=True, text=True
        )

        assert result.returncode == 0
        # Should return JSON list of templates

    def test_cli_use_template(self):
        """Test using template to provision resources via CLI."""
        result = subprocess.run(
            [
                "azlin",
                "template",
                "use",
                "--name",
                "vm-basic",
                "--parameters",
                "location=eastus,vmSize=Standard_D2s_v3",
            ],
            capture_output=True,
            text=True,
        )

        # Should succeed or fail gracefully with clear message
        assert result.returncode in [0, 1]

    def test_cli_list_versions(self):
        """Test listing template versions via CLI."""
        result = subprocess.run(
            ["azlin", "template", "versions", "--name", "vm-basic"], capture_output=True, text=True
        )

        assert result.returncode == 0
        # Should list versions

    def test_cli_template_analytics(self):
        """Test viewing template analytics via CLI."""
        result = subprocess.run(
            ["azlin", "template", "analytics", "--name", "vm-basic"], capture_output=True, text=True
        )

        assert result.returncode == 0
        # Should show usage statistics


class TestTemplateCompositionE2E:
    """End-to-end tests for template composition."""

    def test_cli_create_composite_template(self):
        """Test creating composite template via CLI."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create base template
            base_path = Path(tmpdir) / "base.json"
            base_data = {
                "metadata": {
                    "name": "network-base",
                    "version": "1.0.0",
                    "description": "Base network",
                    "author": "test",
                },
                "content": {"resources": [{"type": "Microsoft.Network/virtualNetworks"}]},
            }
            base_path.write_text(json.dumps(base_data))

            # Publish base
            subprocess.run(["azlin", "template", "publish", str(base_path)], check=True)

            # Create child that extends base
            child_path = Path(tmpdir) / "child.json"
            child_data = {
                "metadata": {
                    "name": "network-extended",
                    "version": "1.0.0",
                    "description": "Extended network",
                    "author": "test",
                    "extends": "network-base",
                },
                "content": {"resources": [{"type": "Microsoft.Network/networkSecurityGroups"}]},
            }
            child_path.write_text(json.dumps(child_data))

            # Resolve composite
            result = subprocess.run(
                [
                    "azlin",
                    "template",
                    "resolve",
                    str(child_path),
                    "--output",
                    str(Path(tmpdir) / "resolved.json"),
                ],
                capture_output=True,
                text=True,
            )

            assert result.returncode == 0

            # Verify resolved template has both resources
            resolved_data = json.loads((Path(tmpdir) / "resolved.json").read_text())
            assert len(resolved_data["content"]["resources"]) == 2


class TestTemplateValidationE2E:
    """End-to-end tests for template validation."""

    def test_cli_validate_with_azure_rules(self):
        """Test validation with Azure-specific rules."""
        with tempfile.TemporaryDirectory() as tmpdir:
            template_path = Path(tmpdir) / "template.json"
            template_data = {
                "metadata": {
                    "name": "azure-template",
                    "version": "1.0.0",
                    "description": "Azure template",
                    "author": "test",
                },
                "content": {
                    "resources": [
                        {
                            "type": "Microsoft.Compute/virtualMachines",
                            "name": "test-vm",
                            "properties": {"location": "eastus", "vmSize": "Standard_D2s_v3"},
                        }
                    ]
                },
            }
            template_path.write_text(json.dumps(template_data))

            result = subprocess.run(
                ["azlin", "template", "validate", str(template_path), "--azure"],
                capture_output=True,
                text=True,
            )

            assert result.returncode == 0

    def test_cli_lint_template(self):
        """Test linting template for best practices."""
        with tempfile.TemporaryDirectory() as tmpdir:
            template_path = Path(tmpdir) / "template.json"
            template_data = {
                "metadata": {
                    "name": "lint-test",
                    "version": "1.0.0",
                    "description": "Test",  # Short description
                    "author": "test",
                },
                "content": {
                    "resources": [
                        {
                            "type": "Microsoft.Compute/virtualMachines",
                            "name": "VM1",  # Should be lowercase
                        }
                    ]
                },
            }
            template_path.write_text(json.dumps(template_data))

            result = subprocess.run(
                ["azlin", "template", "lint", str(template_path)], capture_output=True, text=True
            )

            # Should complete and show issues
            assert result.returncode == 0
            assert "naming" in result.stdout.lower() or "description" in result.stdout.lower()


class TestTemplateAnalyticsE2E:
    """End-to-end tests for template analytics."""

    def test_cli_analytics_report(self):
        """Test generating analytics report via CLI."""
        with tempfile.TemporaryDirectory() as tmpdir:
            report_path = Path(tmpdir) / "report.json"

            result = subprocess.run(
                [
                    "azlin",
                    "template",
                    "analytics",
                    "--name",
                    "vm-basic",
                    "--output",
                    str(report_path),
                    "--format",
                    "json",
                ],
                capture_output=True,
                text=True,
            )

            # Should generate report
            if result.returncode == 0:
                assert report_path.exists()
                report_data = json.loads(report_path.read_text())
                assert "template_name" in report_data

    def test_cli_trending_templates(self):
        """Test viewing trending templates via CLI."""
        result = subprocess.run(
            ["azlin", "template", "trending", "--days", "7", "--limit", "10"],
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0
        # Should list trending templates

    def test_cli_export_analytics(self):
        """Test exporting analytics to CSV."""
        with tempfile.TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "analytics.csv"

            result = subprocess.run(
                ["azlin", "template", "analytics", "--export", str(csv_path), "--format", "csv"],
                capture_output=True,
                text=True,
            )

            if result.returncode == 0:
                assert csv_path.exists()
                content = csv_path.read_text()
                assert "template_name" in content


class TestTemplateMarketplaceE2E:
    """End-to-end tests for template marketplace."""

    def test_complete_marketplace_workflow(self):
        """Test complete marketplace workflow: publish, search, rate, use."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 1. Create template
            template_path = Path(tmpdir) / "marketplace-template.json"
            template_data = {
                "metadata": {
                    "name": "marketplace-vm",
                    "version": "1.0.0",
                    "description": "Marketplace VM template",
                    "author": "publisher",
                    "tags": ["compute", "vm", "marketplace"],
                },
                "content": {"resources": [{"type": "Microsoft.Compute/virtualMachines"}]},
            }
            template_path.write_text(json.dumps(template_data))

            # 2. Publish
            publish_result = subprocess.run(
                ["azlin", "template", "publish", str(template_path)], capture_output=True, text=True
            )
            assert publish_result.returncode == 0

            # 3. Search
            search_result = subprocess.run(
                ["azlin", "template", "search", "--tag", "marketplace"],
                capture_output=True,
                text=True,
            )
            assert search_result.returncode == 0
            assert "marketplace-vm" in search_result.stdout

            # 4. Rate
            rate_result = subprocess.run(
                ["azlin", "template", "rate", "--name", "marketplace-vm", "--rating", "5"],
                capture_output=True,
                text=True,
            )
            # May succeed or need authentication

            # 5. View details
            details_result = subprocess.run(
                ["azlin", "template", "show", "--name", "marketplace-vm"],
                capture_output=True,
                text=True,
            )
            assert details_result.returncode == 0


class TestRealWorldScenarios:
    """End-to-end tests for real-world scenarios."""

    def test_infrastructure_deployment_scenario(self):
        """Test complete infrastructure deployment using templates."""
        # Scenario: Deploy VM with network and storage using templates
        with tempfile.TemporaryDirectory() as tmpdir:
            # Use composite template that includes network, storage, and VM
            result = subprocess.run(
                [
                    "azlin",
                    "template",
                    "deploy",
                    "--name",
                    "complete-infrastructure",
                    "--parameters",
                    "location=eastus,environment=dev",
                    "--dry-run",  # Don't actually deploy
                ],
                capture_output=True,
                text=True,
            )

            # Should generate deployment plan
            assert result.returncode == 0 or "dry-run" in result.stdout.lower()

    def test_template_versioning_scenario(self):
        """Test real-world template versioning scenario."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create v1.0.0
            v1_path = Path(tmpdir) / "v1.json"
            v1_data = {
                "metadata": {
                    "name": "evolving-template",
                    "version": "1.0.0",
                    "description": "Version 1",
                    "author": "dev",
                },
                "content": {"resources": [{"type": "vm", "size": "small"}]},
            }
            v1_path.write_text(json.dumps(v1_data))

            # Publish v1
            subprocess.run(["azlin", "template", "publish", str(v1_path)], check=True)

            # Create v2.0.0 with breaking changes
            v2_data = v1_data.copy()
            v2_data["metadata"]["version"] = "2.0.0"
            v2_data["content"]["resources"][0]["size"] = "large"

            v2_path = Path(tmpdir) / "v2.json"
            v2_path.write_text(json.dumps(v2_data))

            # Publish v2
            result = subprocess.run(
                ["azlin", "template", "publish", str(v2_path)], capture_output=True, text=True
            )

            assert result.returncode == 0

            # List versions
            versions_result = subprocess.run(
                ["azlin", "template", "versions", "--name", "evolving-template"],
                capture_output=True,
                text=True,
            )

            assert versions_result.returncode == 0
            assert "1.0.0" in versions_result.stdout
            assert "2.0.0" in versions_result.stdout

    def test_collaborative_development_scenario(self):
        """Test collaborative template development scenario."""
        # Scenario: Multiple developers contributing to same template
        with tempfile.TemporaryDirectory() as tmpdir:
            # Dev1: Create base
            base_path = Path(tmpdir) / "base.json"
            base_data = {
                "metadata": {
                    "name": "collab-template",
                    "version": "1.0.0",
                    "description": "Collaborative template",
                    "author": "dev1",
                },
                "content": {"resources": []},
            }
            base_path.write_text(json.dumps(base_data))
            subprocess.run(["azlin", "template", "publish", str(base_path)], check=True)

            # Dev2: Update to v1.1.0
            v1_1_data = base_data.copy()
            v1_1_data["metadata"]["version"] = "1.1.0"
            v1_1_data["metadata"]["author"] = "dev2"
            v1_1_data["content"]["resources"].append({"type": "network"})

            v1_1_path = Path(tmpdir) / "v1_1.json"
            v1_1_path.write_text(json.dumps(v1_1_data))
            subprocess.run(["azlin", "template", "publish", str(v1_1_path)], check=True)

            # Dev3: Update to v1.2.0
            v1_2_data = v1_1_data.copy()
            v1_2_data["metadata"]["version"] = "1.2.0"
            v1_2_data["metadata"]["author"] = "dev3"
            v1_2_data["content"]["resources"].append({"type": "storage"})

            v1_2_path = Path(tmpdir) / "v1_2.json"
            v1_2_path.write_text(json.dumps(v1_2_data))

            result = subprocess.run(
                ["azlin", "template", "publish", str(v1_2_path)], capture_output=True, text=True
            )

            assert result.returncode == 0

            # View change history
            history_result = subprocess.run(
                ["azlin", "template", "history", "--name", "collab-template"],
                capture_output=True,
                text=True,
            )

            if history_result.returncode == 0:
                # Should show contributions from all devs
                assert (
                    "dev1" in history_result.stdout
                    or "dev2" in history_result.stdout
                    or "dev3" in history_result.stdout
                )


class TestErrorHandlingE2E:
    """End-to-end tests for error handling."""

    def test_invalid_template_error_handling(self):
        """Test clear error messages for invalid templates."""
        with tempfile.TemporaryDirectory() as tmpdir:
            invalid_path = Path(tmpdir) / "invalid.json"
            invalid_path.write_text("not valid json")

            result = subprocess.run(
                ["azlin", "template", "validate", str(invalid_path)], capture_output=True, text=True
            )

            assert result.returncode != 0
            assert "invalid" in result.stderr.lower() or "error" in result.stderr.lower()

    def test_missing_dependency_error_handling(self):
        """Test clear error for missing template dependencies."""
        with tempfile.TemporaryDirectory() as tmpdir:
            template_path = Path(tmpdir) / "template.json"
            template_data = {
                "metadata": {
                    "name": "dependent-template",
                    "version": "1.0.0",
                    "description": "Has dependencies",
                    "author": "test",
                    "dependencies": {"nonexistent-template": ">=1.0.0"},
                },
                "content": {},
            }
            template_path.write_text(json.dumps(template_data))

            result = subprocess.run(
                ["azlin", "template", "resolve", str(template_path)], capture_output=True, text=True
            )

            assert result.returncode != 0
            assert "dependency" in result.stderr.lower() or "not found" in result.stderr.lower()
