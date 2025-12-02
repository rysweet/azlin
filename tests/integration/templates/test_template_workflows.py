"""Integration tests for complete template workflows.

Test coverage: End-to-end template workflows combining multiple features.

These tests follow TDD - they should FAIL initially until implementation is complete.
"""

import pytest
from pathlib import Path
from datetime import datetime
import tempfile


class TestTemplateCreationWorkflow:
    """Test complete template creation workflow."""

    def test_create_and_register_new_template(self):
        """Test creating new template and registering in marketplace."""
        from azlin.templates.versioning import TemplateMetadata, TemplateVersion, VersionedTemplate
        from azlin.templates.marketplace import TemplateRegistry
        from azlin.templates.validation import TemplateValidator

        # Create template
        metadata = TemplateMetadata(
            name="vm-integration-test",
            version=TemplateVersion(1, 0, 0),
            description="Integration test template",
            author="test-user",
            created_at=datetime.now(),
            tags=["test", "integration"]
        )

        template = VersionedTemplate(
            metadata=metadata,
            content={
                "resources": [
                    {"type": "Microsoft.Compute/virtualMachines", "name": "test-vm"}
                ]
            }
        )

        # Validate
        validator = TemplateValidator()
        validation_result = validator.validate(template.to_dict())
        assert validation_result.is_valid

        # Register
        registry = TemplateRegistry()
        registry.register(template)

        # Verify
        retrieved = registry.get("vm-integration-test")
        assert retrieved.metadata.name == "vm-integration-test"

    def test_create_template_with_validation_failure(self):
        """Test template creation workflow with validation failure."""
        from azlin.templates.versioning import TemplateMetadata, TemplateVersion, VersionedTemplate
        from azlin.templates.validation import TemplateValidator

        # Create invalid template (missing required fields)
        template = VersionedTemplate(
            metadata=TemplateMetadata(
                name="",  # Empty name (invalid)
                version=TemplateVersion(1, 0, 0),
                description="Invalid",
                author="test",
                created_at=datetime.now()
            ),
            content={}
        )

        # Validation should fail
        validator = TemplateValidator()
        result = validator.validate(template.to_dict())

        assert result.is_valid is False
        assert len(result.errors) > 0


class TestTemplateVersioningWorkflow:
    """Test template versioning workflows."""

    def test_update_template_version_with_tracking(self):
        """Test updating template version with automatic change tracking."""
        from azlin.templates.versioning import TemplateMetadata, TemplateVersion, VersionedTemplate
        from azlin.templates.marketplace import TemplateRegistry

        registry = TemplateRegistry()

        # Create initial version
        template = VersionedTemplate(
            metadata=TemplateMetadata(
                name="vm-versioned",
                version=TemplateVersion(1, 0, 0),
                description="Initial version",
                author="test",
                created_at=datetime.now()
            ),
            content={"resources": []}
        )

        registry.register(template)

        # Update to new version
        template.update_version(
            new_version=TemplateVersion(1, 1, 0),
            author="test",
            change_type="minor",
            description="Added new feature"
        )

        registry.update_version("vm-versioned", template)

        # Verify version and history
        retrieved = registry.get("vm-versioned")
        assert retrieved.metadata.version.minor == 1
        assert len(retrieved.change_history) == 1

    def test_version_rollback_workflow(self):
        """Test rolling back to previous template version."""
        from azlin.templates.versioning import TemplateMetadata, TemplateVersion, VersionedTemplate
        from azlin.templates.marketplace import TemplateRegistry

        registry = TemplateRegistry()

        # Create versions v1.0.0 and v2.0.0
        template_v1 = VersionedTemplate(
            metadata=TemplateMetadata(
                name="vm-rollback",
                version=TemplateVersion(1, 0, 0),
                description="Version 1",
                author="test",
                created_at=datetime.now()
            ),
            content={"resources": [{"type": "vm", "size": "small"}]}
        )

        registry.register(template_v1)

        # Update to v2
        template_v2 = VersionedTemplate(
            metadata=TemplateMetadata(
                name="vm-rollback",
                version=TemplateVersion(2, 0, 0),
                description="Version 2",
                author="test",
                created_at=datetime.now()
            ),
            content={"resources": [{"type": "vm", "size": "large"}]}
        )

        registry.update_version("vm-rollback", template_v2)

        # Rollback to v1
        registry.rollback_version("vm-rollback", TemplateVersion(1, 0, 0))

        retrieved = registry.get("vm-rollback")
        assert retrieved.metadata.version.major == 1
        assert retrieved.content["resources"][0]["size"] == "small"


class TestTemplateCompositionWorkflow:
    """Test template composition and inheritance workflows."""

    def test_create_composite_template_from_base(self):
        """Test creating composite template from base template."""
        from azlin.templates.composition import CompositeTemplate, TemplateResolver
        from azlin.templates.marketplace import TemplateRegistry
        from azlin.templates.versioning import VersionedTemplate, TemplateMetadata, TemplateVersion

        registry = TemplateRegistry()

        # Register base template
        base = VersionedTemplate(
            metadata=TemplateMetadata(
                name="network-base",
                version=TemplateVersion(1, 0, 0),
                description="Base network",
                author="test",
                created_at=datetime.now()
            ),
            content={
                "resources": [
                    {"type": "Microsoft.Network/virtualNetworks", "name": "vnet"}
                ]
            }
        )

        registry.register(base)

        # Create child template
        child_dict = {
            "metadata": {
                "name": "network-extended",
                "version": "1.0.0",
                "extends": "network-base",
                "author": "test"
            },
            "content": {
                "resources": [
                    {"type": "Microsoft.Network/networkSecurityGroups", "name": "nsg"}
                ]
            }
        }

        # Resolve dependencies
        resolver = TemplateResolver(registry)
        composite = CompositeTemplate(child_dict, parent=base.to_dict())
        resolved = composite.resolve()

        # Should have both resources
        assert len(resolved["content"]["resources"]) == 2

    def test_multi_level_composition_workflow(self):
        """Test multi-level template composition."""
        from azlin.templates.composition import CompositeTemplate
        from azlin.templates.marketplace import TemplateRegistry
        from azlin.templates.versioning import VersionedTemplate, TemplateMetadata, TemplateVersion

        registry = TemplateRegistry()

        # Create three-level hierarchy
        base = {
            "metadata": {"name": "base", "version": "1.0.0"},
            "content": {"resources": [{"type": "base-resource"}]}
        }

        middle = {
            "metadata": {"name": "middle", "version": "1.0.0", "extends": "base"},
            "content": {"resources": [{"type": "middle-resource"}]}
        }

        top = {
            "metadata": {"name": "top", "version": "1.0.0", "extends": "middle"},
            "content": {"resources": [{"type": "top-resource"}]}
        }

        # Resolve chain
        middle_composite = CompositeTemplate(middle, parent=base)
        middle_resolved = middle_composite.resolve()

        top_composite = CompositeTemplate(top, parent=middle_resolved)
        final = top_composite.resolve()

        # Should have all three resources
        resource_types = [r["type"] for r in final["content"]["resources"]]
        assert "base-resource" in resource_types
        assert "middle-resource" in resource_types
        assert "top-resource" in resource_types


class TestTemplateValidationWorkflow:
    """Test template validation workflows."""

    def test_validate_and_lint_template(self):
        """Test running both validation and linting."""
        from azlin.templates.validation import TemplateValidator, TemplateLinter

        template = {
            "metadata": {
                "name": "vm-validated",
                "version": "1.0.0",
                "description": "Validated template",
                "author": "test"
            },
            "content": {
                "resources": [
                    {"type": "Microsoft.Compute/virtualMachines", "name": "vm1"}
                ]
            }
        }

        # Validate
        validator = TemplateValidator()
        validation_result = validator.validate(template)
        assert validation_result.is_valid

        # Lint
        linter = TemplateLinter()
        lint_result = linter.lint(template)

        # Should pass both
        assert validation_result.is_valid
        # May have lint suggestions but no errors

    def test_fix_validation_errors_workflow(self):
        """Test workflow of identifying and fixing validation errors."""
        from azlin.templates.validation import TemplateValidator

        # Start with invalid template
        template = {
            "metadata": {
                "name": "invalid-template",
                "version": "invalid-version",  # Error
                "description": "",  # Error (empty)
                "author": "test"
            },
            "content": {}
        }

        validator = TemplateValidator()
        result1 = validator.validate(template)
        assert result1.is_valid is False

        # Fix errors
        template["metadata"]["version"] = "1.0.0"
        template["metadata"]["description"] = "Fixed template"

        result2 = validator.validate(template)
        assert result2.is_valid is True


class TestTemplateMarketplaceWorkflow:
    """Test marketplace discovery and sharing workflows."""

    def test_discover_and_use_template(self):
        """Test discovering template in marketplace and using it."""
        from azlin.templates.marketplace import TemplateRegistry
        from azlin.templates.versioning import VersionedTemplate, TemplateMetadata, TemplateVersion
        from azlin.templates.analytics import AnalyticsTracker

        with tempfile.TemporaryDirectory() as tmpdir:
            registry = TemplateRegistry()
            tracker = AnalyticsTracker(db_path=Path(tmpdir) / "analytics.db")

            # Register template
            template = VersionedTemplate(
                metadata=TemplateMetadata(
                    name="vm-marketplace",
                    version=TemplateVersion(1, 0, 0),
                    description="Marketplace template",
                    author="author1",
                    created_at=datetime.now(),
                    tags=["compute", "vm"]
                ),
                content={}
            )

            registry.register(template)

            # User searches
            results = registry.search(tags=["compute"])
            assert len(results) > 0

            # User uses template
            found_template = results[0]
            tracker.record_usage(
                template_name=found_template.metadata.name,
                user_id="user1",
                timestamp=datetime.now()
            )

            # Verify analytics
            usage_count = tracker.get_usage_count("vm-marketplace")
            assert usage_count == 1

    def test_share_and_import_template_workflow(self):
        """Test sharing template and importing it elsewhere."""
        from azlin.templates.marketplace import TemplateRegistry
        from azlin.templates.versioning import VersionedTemplate, TemplateMetadata, TemplateVersion

        with tempfile.TemporaryDirectory() as tmpdir:
            # Author creates and exports template
            registry1 = TemplateRegistry()

            template = VersionedTemplate(
                metadata=TemplateMetadata(
                    name="shared-template",
                    version=TemplateVersion(1, 0, 0),
                    description="Shared template",
                    author="author1",
                    created_at=datetime.now()
                ),
                content={"resources": []}
            )

            registry1.register(template)

            export_path = Path(tmpdir) / "shared.json"
            registry1.export_template("shared-template", export_path)

            # Another user imports template
            registry2 = TemplateRegistry()
            registry2.import_template(export_path)

            # Verify imported
            imported = registry2.get("shared-template")
            assert imported.metadata.name == "shared-template"


class TestTemplateAnalyticsWorkflow:
    """Test analytics tracking workflows."""

    def test_track_template_usage_lifecycle(self):
        """Test tracking complete template usage lifecycle."""
        from azlin.templates.analytics import AnalyticsTracker, AnalyticsReporter

        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = AnalyticsTracker(db_path=Path(tmpdir) / "analytics.db")
            reporter = AnalyticsReporter(db_path=Path(tmpdir) / "analytics.db")

            # Record usage
            tracker.record_usage(
                template_name="vm-analytics",
                user_id="user1",
                timestamp=datetime.now(),
                metadata={"success": True, "duration_seconds": 45.0}
            )

            tracker.record_usage(
                template_name="vm-analytics",
                user_id="user2",
                timestamp=datetime.now(),
                metadata={"success": True, "duration_seconds": 50.0}
            )

            # Generate report
            report = reporter.generate_template_report("vm-analytics")

            assert report.total_uses == 2
            assert report.unique_users == 2
            assert report.success_rate == 100.0

    def test_trending_templates_workflow(self):
        """Test identifying and displaying trending templates."""
        from azlin.templates.analytics import AnalyticsTracker
        from azlin.templates.marketplace import TemplateRegistry
        from azlin.templates.versioning import VersionedTemplate, TemplateMetadata, TemplateVersion
        from datetime import timedelta

        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = AnalyticsTracker(db_path=Path(tmpdir) / "analytics.db")
            registry = TemplateRegistry()

            # Register templates
            for i in range(3):
                template = VersionedTemplate(
                    metadata=TemplateMetadata(
                        name=f"template-{i}",
                        version=TemplateVersion(1, 0, 0),
                        description=f"Template {i}",
                        author="test",
                        created_at=datetime.now()
                    ),
                    content={}
                )
                registry.register(template)

            # Create trending pattern (template-0 has increasing usage)
            now = datetime.now()
            week_ago = now - timedelta(days=7)

            tracker.record_usage("template-0", "user1", week_ago)
            for i in range(10):
                tracker.record_usage("template-0", f"user{i}", now)

            # Other templates have flat usage
            tracker.record_usage("template-1", "user1", week_ago)
            tracker.record_usage("template-1", "user2", now)

            # Get trending
            trending = tracker.get_trending_templates(days=7, limit=3)

            assert trending[0].name == "template-0"


class TestEndToEndTemplateWorkflow:
    """Test complete end-to-end template workflows."""

    def test_complete_template_lifecycle(self):
        """Test complete template lifecycle from creation to usage."""
        from azlin.templates.versioning import TemplateMetadata, TemplateVersion, VersionedTemplate
        from azlin.templates.validation import TemplateValidator, TemplateLinter
        from azlin.templates.marketplace import TemplateRegistry
        from azlin.templates.analytics import AnalyticsTracker

        with tempfile.TemporaryDirectory() as tmpdir:
            # 1. Create template
            template = VersionedTemplate(
                metadata=TemplateMetadata(
                    name="vm-e2e",
                    version=TemplateVersion(1, 0, 0),
                    description="End-to-end test template",
                    author="developer",
                    created_at=datetime.now(),
                    tags=["e2e", "test"]
                ),
                content={
                    "resources": [
                        {"type": "Microsoft.Compute/virtualMachines", "name": "vm1"}
                    ]
                }
            )

            # 2. Validate
            validator = TemplateValidator()
            validation = validator.validate(template.to_dict())
            assert validation.is_valid

            # 3. Lint
            linter = TemplateLinter()
            lint_result = linter.lint(template.to_dict())
            # May have suggestions

            # 4. Register in marketplace
            registry = TemplateRegistry()
            registry.register(template)

            # 5. Search and discover
            results = registry.search(tags=["e2e"])
            assert len(results) == 1

            # 6. Rate template
            registry.rate_template("vm-e2e", "user1", 5)

            # 7. Track usage
            tracker = AnalyticsTracker(db_path=Path(tmpdir) / "analytics.db")
            tracker.record_usage("vm-e2e", "user1", datetime.now())

            # 8. Update version
            template.update_version(
                new_version=TemplateVersion(1, 1, 0),
                author="developer",
                change_type="minor",
                description="Added features"
            )

            registry.update_version("vm-e2e", template)

            # Verify entire lifecycle
            final_template = registry.get("vm-e2e")
            assert final_template.metadata.version.minor == 1
            assert len(final_template.change_history) == 1

            usage_count = tracker.get_usage_count("vm-e2e")
            assert usage_count == 1

            rating_stats = registry.get_rating_stats("vm-e2e")
            assert rating_stats["average"] == 5.0

    def test_collaborative_template_development(self):
        """Test collaborative template development workflow."""
        from azlin.templates.versioning import TemplateMetadata, TemplateVersion, VersionedTemplate
        from azlin.templates.marketplace import TemplateRegistry

        registry = TemplateRegistry()

        # Developer 1 creates base template
        base_template = VersionedTemplate(
            metadata=TemplateMetadata(
                name="collab-template",
                version=TemplateVersion(1, 0, 0),
                description="Collaborative template",
                author="dev1",
                created_at=datetime.now()
            ),
            content={"resources": [{"type": "vm"}]}
        )

        registry.register(base_template)

        # Developer 2 extends it
        base_template.update_version(
            new_version=TemplateVersion(1, 1, 0),
            author="dev2",
            change_type="minor",
            description="Added networking"
        )

        base_template.content["resources"].append({"type": "network"})
        registry.update_version("collab-template", base_template)

        # Developer 3 makes further improvements
        base_template.update_version(
            new_version=TemplateVersion(1, 2, 0),
            author="dev3",
            change_type="minor",
            description="Added storage"
        )

        base_template.content["resources"].append({"type": "storage"})
        registry.update_version("collab-template", base_template)

        # Verify collaborative history
        final = registry.get("collab-template")
        assert final.metadata.version.minor == 2
        assert len(final.change_history) == 3
        assert len(final.content["resources"]) == 3

        # Verify different authors
        authors = [change.author for change in final.change_history]
        assert "dev1" in authors
        assert "dev2" in authors
        assert "dev3" in authors
