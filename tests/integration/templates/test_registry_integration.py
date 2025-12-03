"""Integration tests for template registry operations.

Test coverage: Registry operations with validation, analytics, and file system.

These tests follow TDD - they should FAIL initially until implementation is complete.
"""

import tempfile
from datetime import datetime
from pathlib import Path

import pytest


class TestRegistryValidationIntegration:
    """Test integration between registry and validation."""

    def test_registry_validates_on_register(self):
        """Test registry automatically validates templates on registration."""
        from azlin.templates.marketplace import TemplateRegistry
        from azlin.templates.versioning import TemplateMetadata, TemplateVersion, VersionedTemplate

        registry = TemplateRegistry(auto_validate=True)

        # Try to register invalid template
        invalid_template = VersionedTemplate(
            metadata=TemplateMetadata(
                name="",  # Invalid
                version=TemplateVersion(1, 0, 0),
                description="Invalid",
                author="test",
                created_at=datetime.now(),
            ),
            content={},
        )

        with pytest.raises(ValueError, match="validation"):
            registry.register(invalid_template)

    def test_registry_with_custom_validators(self):
        """Test registry with custom validation rules."""
        from azlin.templates.marketplace import TemplateRegistry
        from azlin.templates.versioning import TemplateMetadata, TemplateVersion, VersionedTemplate

        def custom_validator(template):
            if "production" in template.metadata.tags:
                if not template.metadata.description.startswith("[PROD]"):
                    raise ValueError("Production templates must have [PROD] prefix")

        registry = TemplateRegistry(validators=[custom_validator])

        template = VersionedTemplate(
            metadata=TemplateMetadata(
                name="prod-template",
                version=TemplateVersion(1, 0, 0),
                description="Missing prefix",
                author="test",
                created_at=datetime.now(),
                tags=["production"],
            ),
            content={},
        )

        with pytest.raises(ValueError, match="PROD"):
            registry.register(template)


class TestRegistryAnalyticsIntegration:
    """Test integration between registry and analytics."""

    def test_registry_tracks_usage_automatically(self):
        """Test registry automatically tracks template usage."""
        from azlin.templates.analytics import AnalyticsTracker
        from azlin.templates.marketplace import TemplateRegistry
        from azlin.templates.versioning import TemplateMetadata, TemplateVersion, VersionedTemplate

        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = AnalyticsTracker(db_path=Path(tmpdir) / "analytics.db")
            registry = TemplateRegistry(analytics_tracker=tracker)

            template = VersionedTemplate(
                metadata=TemplateMetadata(
                    name="tracked-template",
                    version=TemplateVersion(1, 0, 0),
                    description="Test",
                    author="test",
                    created_at=datetime.now(),
                ),
                content={},
            )

            registry.register(template)

            # Simulate usage
            registry.use_template("tracked-template", user_id="user1")

            # Verify analytics recorded
            usage_count = tracker.get_usage_count("tracked-template")
            assert usage_count == 1

    def test_popular_templates_based_on_analytics(self):
        """Test getting popular templates based on analytics data."""
        from azlin.templates.analytics import AnalyticsTracker
        from azlin.templates.marketplace import TemplateRegistry
        from azlin.templates.versioning import TemplateMetadata, TemplateVersion, VersionedTemplate

        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = AnalyticsTracker(db_path=Path(tmpdir) / "analytics.db")
            registry = TemplateRegistry(analytics_tracker=tracker)

            # Register multiple templates
            for i in range(5):
                template = VersionedTemplate(
                    metadata=TemplateMetadata(
                        name=f"template-{i}",
                        version=TemplateVersion(1, 0, 0),
                        description=f"Template {i}",
                        author="test",
                        created_at=datetime.now(),
                    ),
                    content={},
                )
                registry.register(template)

                # Template 0 used most
                for j in range(5 - i):
                    registry.use_template(f"template-{i}", f"user{j}")

            # Get popular templates
            popular = registry.get_popular_templates(limit=3)

            assert len(popular) == 3
            assert popular[0].metadata.name == "template-0"


class TestRegistryFilesystemIntegration:
    """Test integration between registry and file system."""

    def test_registry_persists_to_disk(self):
        """Test registry persists templates to disk."""
        from azlin.templates.marketplace import TemplateRegistry
        from azlin.templates.versioning import TemplateMetadata, TemplateVersion, VersionedTemplate

        with tempfile.TemporaryDirectory() as tmpdir:
            registry_path = Path(tmpdir) / "registry"

            # Create registry with persistence
            registry1 = TemplateRegistry(storage_path=registry_path)

            template = VersionedTemplate(
                metadata=TemplateMetadata(
                    name="persisted-template",
                    version=TemplateVersion(1, 0, 0),
                    description="Persisted",
                    author="test",
                    created_at=datetime.now(),
                ),
                content={},
            )

            registry1.register(template)
            registry1.save()

            # Create new registry instance - should load from disk
            registry2 = TemplateRegistry(storage_path=registry_path)
            registry2.load()

            retrieved = registry2.get("persisted-template")
            assert retrieved.metadata.name == "persisted-template"

    def test_registry_import_export_workflow(self):
        """Test complete import/export workflow with file system."""
        from azlin.templates.marketplace import TemplateRegistry
        from azlin.templates.versioning import TemplateMetadata, TemplateVersion, VersionedTemplate

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create and export
            registry1 = TemplateRegistry()

            template = VersionedTemplate(
                metadata=TemplateMetadata(
                    name="export-template",
                    version=TemplateVersion(1, 0, 0),
                    description="Export test",
                    author="test",
                    created_at=datetime.now(),
                ),
                content={"resources": []},
            )

            registry1.register(template)

            export_dir = Path(tmpdir) / "exports"
            export_dir.mkdir()

            registry1.export_all(export_dir)

            # Import into new registry
            registry2 = TemplateRegistry()
            registry2.import_directory(export_dir)

            # Verify import
            imported = registry2.get("export-template")
            assert imported.metadata.name == "export-template"


class TestCompositionValidationIntegration:
    """Test integration between composition and validation."""

    def test_validate_composite_template(self):
        """Test validating composite template after resolution."""
        from azlin.templates.composition import CompositeTemplate
        from azlin.templates.validation import TemplateValidator

        base = {
            "metadata": {"name": "base", "version": "1.0.0"},
            "content": {"resources": [{"type": "Microsoft.Compute/virtualMachines"}]},
        }

        child = {
            "metadata": {"name": "child", "version": "1.0.0", "extends": "base"},
            "content": {"resources": [{"type": "Microsoft.Network/networkInterfaces"}]},
        }

        composite = CompositeTemplate(child, parent=base)
        resolved = composite.resolve()

        # Validate resolved template
        validator = TemplateValidator()
        result = validator.validate(resolved)

        assert result.is_valid is True

    def test_composition_preserves_validation_metadata(self):
        """Test composition preserves validation-related metadata."""
        from azlin.templates.composition import CompositeTemplate

        base = {
            "metadata": {"name": "base", "version": "1.0.0", "validation_schema": "azure-arm-v1"},
            "content": {},
        }

        child = {
            "metadata": {"name": "child", "version": "1.0.0", "extends": "base"},
            "content": {},
        }

        composite = CompositeTemplate(child, parent=base)
        resolved = composite.resolve()

        assert "validation_schema" in resolved["metadata"]
        assert resolved["metadata"]["validation_schema"] == "azure-arm-v1"


class TestVersioningAnalyticsIntegration:
    """Test integration between versioning and analytics."""

    def test_analytics_tracks_version_usage(self):
        """Test analytics tracks which template versions are used."""
        from azlin.templates.analytics import AnalyticsTracker

        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = AnalyticsTracker(db_path=Path(tmpdir) / "analytics.db")

            # Track different versions
            tracker.record_usage(
                "my-template", "user1", datetime.now(), metadata={"version": "1.0.0"}
            )

            tracker.record_usage(
                "my-template", "user2", datetime.now(), metadata={"version": "2.0.0"}
            )

            tracker.record_usage(
                "my-template", "user3", datetime.now(), metadata={"version": "2.0.0"}
            )

            # Get version usage stats
            version_stats = tracker.get_version_usage("my-template")

            assert version_stats["1.0.0"] == 1
            assert version_stats["2.0.0"] == 2

    def test_version_deprecation_workflow(self):
        """Test marking versions as deprecated and tracking usage."""
        from azlin.templates.analytics import AnalyticsTracker
        from azlin.templates.marketplace import TemplateRegistry
        from azlin.templates.versioning import TemplateMetadata, TemplateVersion, VersionedTemplate

        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = AnalyticsTracker(db_path=Path(tmpdir) / "analytics.db")
            registry = TemplateRegistry(analytics_tracker=tracker)

            # Register old version
            old_template = VersionedTemplate(
                metadata=TemplateMetadata(
                    name="deprecation-test",
                    version=TemplateVersion(1, 0, 0),
                    description="Old version",
                    author="test",
                    created_at=datetime.now(),
                ),
                content={},
            )

            registry.register(old_template)

            # Mark as deprecated
            registry.deprecate_version("deprecation-test", TemplateVersion(1, 0, 0))

            # Track usage of deprecated version
            registry.use_template("deprecation-test", "user1")

            # Should record warning in analytics
            events = tracker.get_usage_history("deprecation-test")
            assert any("deprecated" in str(e.metadata) for e in events)


class TestMultiComponentIntegration:
    """Test integration across multiple components."""

    def test_complete_template_registration_workflow(self):
        """Test complete workflow: validate, compose, register, track."""
        from azlin.templates.analytics import AnalyticsTracker
        from azlin.templates.marketplace import TemplateRegistry
        from azlin.templates.validation import TemplateValidator
        from azlin.templates.versioning import TemplateMetadata, TemplateVersion, VersionedTemplate

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create template
            template = VersionedTemplate(
                metadata=TemplateMetadata(
                    name="complete-workflow",
                    version=TemplateVersion(1, 0, 0),
                    description="Complete workflow test",
                    author="test",
                    created_at=datetime.now(),
                    tags=["integration"],
                ),
                content={
                    "resources": [{"type": "Microsoft.Compute/virtualMachines", "name": "vm1"}]
                },
            )

            # Validate
            validator = TemplateValidator()
            validation = validator.validate(template.to_dict())
            assert validation.is_valid

            # Register
            tracker = AnalyticsTracker(db_path=Path(tmpdir) / "analytics.db")
            registry = TemplateRegistry(analytics_tracker=tracker)
            registry.register(template)

            # Use
            registry.use_template("complete-workflow", "user1")

            # Rate
            registry.rate_template("complete-workflow", "user1", 5)

            # Verify all components worked
            assert registry.exists("complete-workflow")
            assert tracker.get_usage_count("complete-workflow") == 1
            assert registry.get_rating_stats("complete-workflow")["average"] == 5.0

    def test_template_update_propagation(self):
        """Test template updates propagate across all systems."""
        from azlin.templates.analytics import AnalyticsTracker
        from azlin.templates.marketplace import TemplateRegistry
        from azlin.templates.versioning import TemplateMetadata, TemplateVersion, VersionedTemplate

        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = AnalyticsTracker(db_path=Path(tmpdir) / "analytics.db")
            registry = TemplateRegistry(analytics_tracker=tracker)

            # Register v1
            template_v1 = VersionedTemplate(
                metadata=TemplateMetadata(
                    name="propagation-test",
                    version=TemplateVersion(1, 0, 0),
                    description="Version 1",
                    author="test",
                    created_at=datetime.now(),
                ),
                content={},
            )

            registry.register(template_v1)

            # Use v1
            registry.use_template("propagation-test", "user1")

            # Update to v2
            template_v2 = VersionedTemplate(
                metadata=TemplateMetadata(
                    name="propagation-test",
                    version=TemplateVersion(2, 0, 0),
                    description="Version 2",
                    author="test",
                    created_at=datetime.now(),
                ),
                content={},
            )

            registry.update_version("propagation-test", template_v2)

            # Use v2
            registry.use_template("propagation-test", "user2")

            # Analytics should track both versions
            total_usage = tracker.get_usage_count("propagation-test")
            assert total_usage == 2

            # Registry should show latest version
            current = registry.get("propagation-test")
            assert current.metadata.version.major == 2


class TestConcurrencyIntegration:
    """Test concurrent operations integration."""

    def test_concurrent_registrations(self):
        """Test multiple concurrent template registrations."""
        import threading

        from azlin.templates.marketplace import TemplateRegistry
        from azlin.templates.versioning import TemplateMetadata, TemplateVersion, VersionedTemplate

        registry = TemplateRegistry()

        def register_template(i):
            template = VersionedTemplate(
                metadata=TemplateMetadata(
                    name=f"concurrent-{i}",
                    version=TemplateVersion(1, 0, 0),
                    description=f"Template {i}",
                    author="test",
                    created_at=datetime.now(),
                ),
                content={},
            )
            registry.register(template)

        threads = [threading.Thread(target=register_template, args=(i,)) for i in range(10)]

        for t in threads:
            t.start()

        for t in threads:
            t.join()

        # All templates should be registered
        assert registry.count() == 10

    def test_concurrent_analytics_recording(self):
        """Test concurrent analytics recording."""
        import threading

        from azlin.templates.analytics import AnalyticsTracker

        with tempfile.TemporaryDirectory() as tmpdir:
            tracker = AnalyticsTracker(db_path=Path(tmpdir) / "analytics.db")

            def record_usage(i):
                tracker.record_usage("concurrent-template", f"user{i}", datetime.now())

            threads = [threading.Thread(target=record_usage, args=(i,)) for i in range(50)]

            for t in threads:
                t.start()

            for t in threads:
                t.join()

            # All usages should be recorded
            count = tracker.get_usage_count("concurrent-template")
            assert count == 50


class TestErrorRecoveryIntegration:
    """Test error recovery across components."""

    def test_rollback_on_validation_failure(self):
        """Test transaction rollback when validation fails."""
        from azlin.templates.marketplace import TemplateRegistry
        from azlin.templates.versioning import TemplateMetadata, TemplateVersion, VersionedTemplate

        registry = TemplateRegistry(auto_validate=True, transactional=True)

        # Register valid template
        valid = VersionedTemplate(
            metadata=TemplateMetadata(
                name="rollback-test",
                version=TemplateVersion(1, 0, 0),
                description="Valid",
                author="test",
                created_at=datetime.now(),
            ),
            content={},
        )

        registry.register(valid)

        # Try to update with invalid version
        invalid = VersionedTemplate(
            metadata=TemplateMetadata(
                name="rollback-test",
                version=TemplateVersion(2, 0, 0),
                description="",  # Invalid
                author="test",
                created_at=datetime.now(),
            ),
            content={},
        )

        with pytest.raises(ValueError):
            registry.update_version("rollback-test", invalid)

        # Original should still be intact
        current = registry.get("rollback-test")
        assert current.metadata.version.major == 1
        assert current.metadata.description == "Valid"

    def test_analytics_failure_doesnt_block_registry(self):
        """Test registry operations continue even if analytics fails."""
        from azlin.templates.analytics import AnalyticsTracker
        from azlin.templates.marketplace import TemplateRegistry
        from azlin.templates.versioning import TemplateMetadata, TemplateVersion, VersionedTemplate

        # Create tracker with invalid DB path
        tracker = AnalyticsTracker(db_path=Path("/invalid/path/analytics.db"))

        # Registry should still work
        registry = TemplateRegistry(analytics_tracker=tracker, fail_on_analytics_error=False)

        template = VersionedTemplate(
            metadata=TemplateMetadata(
                name="resilient-template",
                version=TemplateVersion(1, 0, 0),
                description="Test",
                author="test",
                created_at=datetime.now(),
            ),
            content={},
        )

        # Should succeed despite analytics failure
        registry.register(template)

        assert registry.exists("resilient-template")
