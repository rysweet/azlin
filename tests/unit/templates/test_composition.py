"""Unit tests for composite templates and inheritance.

Test coverage: Composite templates (inheritance via `extends` keyword)

These tests follow TDD - they should FAIL initially until implementation is complete.
"""

import pytest
from datetime import datetime


class TestTemplateInheritance:
    """Test basic template inheritance functionality."""

    def test_simple_template_extends(self):
        """Test template extending another template."""
        from azlin.templates.composition import CompositeTemplate

        base_template = {
            "metadata": {
                "name": "base-vm",
                "version": "1.0.0"
            },
            "content": {
                "resources": [
                    {"type": "Microsoft.Compute/virtualMachines", "name": "vm"}
                ]
            }
        }

        child_template = {
            "metadata": {
                "name": "extended-vm",
                "version": "1.0.0",
                "extends": "base-vm"
            },
            "content": {
                "resources": [
                    {"type": "Microsoft.Network/networkInterfaces", "name": "nic"}
                ]
            }
        }

        composite = CompositeTemplate(child_template, parent=base_template)
        resolved = composite.resolve()

        # Should contain resources from both templates
        assert len(resolved["content"]["resources"]) == 2

    def test_template_extends_override_property(self):
        """Test child template overriding parent properties."""
        from azlin.templates.composition import CompositeTemplate

        base = {
            "metadata": {"name": "base", "version": "1.0.0"},
            "content": {
                "parameters": {"vmSize": "Standard_D2s_v3"}
            }
        }

        child = {
            "metadata": {"name": "child", "version": "1.0.0", "extends": "base"},
            "content": {
                "parameters": {"vmSize": "Standard_D4s_v3"}  # Override
            }
        }

        composite = CompositeTemplate(child, parent=base)
        resolved = composite.resolve()

        assert resolved["content"]["parameters"]["vmSize"] == "Standard_D4s_v3"

    def test_template_extends_missing_parent(self):
        """Test extending nonexistent parent raises error."""
        from azlin.templates.composition import CompositeTemplate

        child = {
            "metadata": {"name": "child", "version": "1.0.0", "extends": "nonexistent"},
            "content": {}
        }

        with pytest.raises(ValueError, match="Parent template.*not found"):
            CompositeTemplate(child, parent=None)

    def test_multi_level_inheritance(self):
        """Test template inheritance with multiple levels."""
        from azlin.templates.composition import CompositeTemplate

        base = {
            "metadata": {"name": "base", "version": "1.0.0"},
            "content": {"resources": [{"type": "base-resource"}]}
        }

        middle = {
            "metadata": {"name": "middle", "version": "1.0.0", "extends": "base"},
            "content": {"resources": [{"type": "middle-resource"}]}
        }

        child = {
            "metadata": {"name": "child", "version": "1.0.0", "extends": "middle"},
            "content": {"resources": [{"type": "child-resource"}]}
        }

        # Build chain: base -> middle -> child
        middle_composite = CompositeTemplate(middle, parent=base)
        child_composite = CompositeTemplate(child, parent=middle_composite.resolve())

        resolved = child_composite.resolve()

        # Should have resources from all three templates
        resource_types = [r["type"] for r in resolved["content"]["resources"]]
        assert "base-resource" in resource_types
        assert "middle-resource" in resource_types
        assert "child-resource" in resource_types

    def test_circular_inheritance_detection(self):
        """Test detecting circular inheritance."""
        from azlin.templates.composition import CompositeTemplate

        template_a = {
            "metadata": {"name": "a", "version": "1.0.0", "extends": "b"},
            "content": {}
        }

        template_b = {
            "metadata": {"name": "b", "version": "1.0.0", "extends": "a"},
            "content": {}
        }

        with pytest.raises(ValueError, match="Circular inheritance"):
            CompositeTemplate(template_a, parent=template_b)


class TestResourceMerging:
    """Test merging resources from parent and child templates."""

    def test_merge_unique_resources(self):
        """Test merging resources with unique names."""
        from azlin.templates.composition import CompositeTemplate

        base = {
            "metadata": {"name": "base", "version": "1.0.0"},
            "content": {
                "resources": [
                    {"name": "vm1", "type": "vm"},
                    {"name": "storage1", "type": "storage"}
                ]
            }
        }

        child = {
            "metadata": {"name": "child", "version": "1.0.0", "extends": "base"},
            "content": {
                "resources": [
                    {"name": "network1", "type": "network"}
                ]
            }
        }

        composite = CompositeTemplate(child, parent=base)
        resolved = composite.resolve()

        assert len(resolved["content"]["resources"]) == 3

    def test_merge_duplicate_resources(self):
        """Test merging resources with duplicate names (child overrides)."""
        from azlin.templates.composition import CompositeTemplate

        base = {
            "metadata": {"name": "base", "version": "1.0.0"},
            "content": {
                "resources": [
                    {"name": "vm1", "type": "vm", "size": "small"}
                ]
            }
        }

        child = {
            "metadata": {"name": "child", "version": "1.0.0", "extends": "base"},
            "content": {
                "resources": [
                    {"name": "vm1", "type": "vm", "size": "large"}  # Override
                ]
            }
        }

        composite = CompositeTemplate(child, parent=base)
        resolved = composite.resolve()

        # Child should override parent
        assert len(resolved["content"]["resources"]) == 1
        assert resolved["content"]["resources"][0]["size"] == "large"

    def test_merge_deep_nested_resources(self):
        """Test merging deeply nested resource properties."""
        from azlin.templates.composition import CompositeTemplate

        base = {
            "metadata": {"name": "base", "version": "1.0.0"},
            "content": {
                "resources": [{
                    "name": "vm1",
                    "properties": {
                        "hardware": {"cpu": 2, "memory": 8},
                        "network": {"subnet": "default"}
                    }
                }]
            }
        }

        child = {
            "metadata": {"name": "child", "version": "1.0.0", "extends": "base"},
            "content": {
                "resources": [{
                    "name": "vm1",
                    "properties": {
                        "hardware": {"cpu": 4}  # Override cpu, keep memory
                    }
                }]
            }
        }

        composite = CompositeTemplate(child, parent=base)
        resolved = composite.resolve()

        vm = resolved["content"]["resources"][0]
        assert vm["properties"]["hardware"]["cpu"] == 4
        assert vm["properties"]["hardware"]["memory"] == 8  # Preserved from parent
        assert vm["properties"]["network"]["subnet"] == "default"  # Preserved


class TestParameterInheritance:
    """Test parameter inheritance and override behavior."""

    def test_inherit_all_parameters(self):
        """Test inheriting all parameters from parent."""
        from azlin.templates.composition import CompositeTemplate

        base = {
            "metadata": {"name": "base", "version": "1.0.0"},
            "content": {
                "parameters": {
                    "location": "eastus",
                    "vmSize": "Standard_D2s_v3",
                    "adminPassword": "secret"
                }
            }
        }

        child = {
            "metadata": {"name": "child", "version": "1.0.0", "extends": "base"},
            "content": {}
        }

        composite = CompositeTemplate(child, parent=base)
        resolved = composite.resolve()

        assert len(resolved["content"]["parameters"]) == 3
        assert resolved["content"]["parameters"]["location"] == "eastus"

    def test_override_specific_parameters(self):
        """Test overriding specific parameters while keeping others."""
        from azlin.templates.composition import CompositeTemplate

        base = {
            "metadata": {"name": "base", "version": "1.0.0"},
            "content": {
                "parameters": {
                    "location": "eastus",
                    "vmSize": "Standard_D2s_v3"
                }
            }
        }

        child = {
            "metadata": {"name": "child", "version": "1.0.0", "extends": "base"},
            "content": {
                "parameters": {
                    "location": "westus"  # Override only location
                }
            }
        }

        composite = CompositeTemplate(child, parent=base)
        resolved = composite.resolve()

        assert resolved["content"]["parameters"]["location"] == "westus"
        assert resolved["content"]["parameters"]["vmSize"] == "Standard_D2s_v3"

    def test_add_new_parameters(self):
        """Test adding new parameters in child template."""
        from azlin.templates.composition import CompositeTemplate

        base = {
            "metadata": {"name": "base", "version": "1.0.0"},
            "content": {
                "parameters": {"location": "eastus"}
            }
        }

        child = {
            "metadata": {"name": "child", "version": "1.0.0", "extends": "base"},
            "content": {
                "parameters": {"vmSize": "Standard_D2s_v3"}  # New parameter
            }
        }

        composite = CompositeTemplate(child, parent=base)
        resolved = composite.resolve()

        assert "location" in resolved["content"]["parameters"]
        assert "vmSize" in resolved["content"]["parameters"]
        assert len(resolved["content"]["parameters"]) == 2


class TestVariableInheritance:
    """Test variable inheritance and scoping."""

    def test_inherit_variables(self):
        """Test inheriting variables from parent."""
        from azlin.templates.composition import CompositeTemplate

        base = {
            "metadata": {"name": "base", "version": "1.0.0"},
            "content": {
                "variables": {
                    "storageAccountName": "storage123",
                    "resourcePrefix": "dev"
                }
            }
        }

        child = {
            "metadata": {"name": "child", "version": "1.0.0", "extends": "base"},
            "content": {}
        }

        composite = CompositeTemplate(child, parent=base)
        resolved = composite.resolve()

        assert "storageAccountName" in resolved["content"]["variables"]
        assert "resourcePrefix" in resolved["content"]["variables"]

    def test_variable_override(self):
        """Test child overriding parent variables."""
        from azlin.templates.composition import CompositeTemplate

        base = {
            "metadata": {"name": "base", "version": "1.0.0"},
            "content": {
                "variables": {"environment": "dev"}
            }
        }

        child = {
            "metadata": {"name": "child", "version": "1.0.0", "extends": "base"},
            "content": {
                "variables": {"environment": "prod"}  # Override
            }
        }

        composite = CompositeTemplate(child, parent=base)
        resolved = composite.resolve()

        assert resolved["content"]["variables"]["environment"] == "prod"


class TestDependencyResolution:
    """Test resolving template dependencies."""

    def test_resolve_single_dependency(self):
        """Test resolving template with single dependency."""
        from azlin.templates.composition import TemplateResolver
        from azlin.templates.marketplace import TemplateRegistry
        from azlin.templates.versioning import VersionedTemplate, TemplateMetadata, TemplateVersion

        registry = TemplateRegistry()

        # Register base template
        base = VersionedTemplate(
            metadata=TemplateMetadata(
                name="base-vm",
                version=TemplateVersion(1, 0, 0),
                description="Base VM",
                author="test",
                created_at=datetime.now()
            ),
            content={"resources": [{"type": "vm"}]}
        )
        registry.register(base)

        # Create child with dependency
        child = VersionedTemplate(
            metadata=TemplateMetadata(
                name="extended-vm",
                version=TemplateVersion(1, 0, 0),
                description="Extended VM",
                author="test",
                created_at=datetime.now(),
                dependencies={"base-vm": ">=1.0.0"}
            ),
            content={"resources": [{"type": "network"}]}
        )

        resolver = TemplateResolver(registry)
        resolved = resolver.resolve_dependencies(child)

        assert resolved is not None
        assert len(resolved.content["resources"]) == 2

    def test_resolve_multiple_dependencies(self):
        """Test resolving template with multiple dependencies."""
        from azlin.templates.composition import TemplateResolver
        from azlin.templates.marketplace import TemplateRegistry
        from azlin.templates.versioning import VersionedTemplate, TemplateMetadata, TemplateVersion

        registry = TemplateRegistry()

        # Register base templates
        network_template = VersionedTemplate(
            metadata=TemplateMetadata(
                name="network-basic",
                version=TemplateVersion(1, 0, 0),
                description="Network",
                author="test",
                created_at=datetime.now()
            ),
            content={"resources": [{"type": "network"}]}
        )

        storage_template = VersionedTemplate(
            metadata=TemplateMetadata(
                name="storage-basic",
                version=TemplateVersion(1, 0, 0),
                description="Storage",
                author="test",
                created_at=datetime.now()
            ),
            content={"resources": [{"type": "storage"}]}
        )

        registry.register(network_template)
        registry.register(storage_template)

        # Create template with multiple dependencies
        vm_template = VersionedTemplate(
            metadata=TemplateMetadata(
                name="vm-complete",
                version=TemplateVersion(1, 0, 0),
                description="Complete VM",
                author="test",
                created_at=datetime.now(),
                dependencies={
                    "network-basic": ">=1.0.0",
                    "storage-basic": ">=1.0.0"
                }
            ),
            content={"resources": [{"type": "vm"}]}
        )

        resolver = TemplateResolver(registry)
        resolved = resolver.resolve_dependencies(vm_template)

        # Should have all resources
        assert len(resolved.content["resources"]) == 3

    def test_resolve_missing_dependency(self):
        """Test resolving template with missing dependency raises error."""
        from azlin.templates.composition import TemplateResolver
        from azlin.templates.marketplace import TemplateRegistry
        from azlin.templates.versioning import VersionedTemplate, TemplateMetadata, TemplateVersion

        registry = TemplateRegistry()

        template = VersionedTemplate(
            metadata=TemplateMetadata(
                name="vm",
                version=TemplateVersion(1, 0, 0),
                description="VM",
                author="test",
                created_at=datetime.now(),
                dependencies={"nonexistent": ">=1.0.0"}
            ),
            content={}
        )

        resolver = TemplateResolver(registry)

        with pytest.raises(ValueError, match="Dependency.*not found"):
            resolver.resolve_dependencies(template)

    def test_resolve_version_conflict(self):
        """Test resolving template with version conflict."""
        from azlin.templates.composition import TemplateResolver
        from azlin.templates.marketplace import TemplateRegistry
        from azlin.templates.versioning import VersionedTemplate, TemplateMetadata, TemplateVersion

        registry = TemplateRegistry()

        # Register old version
        base = VersionedTemplate(
            metadata=TemplateMetadata(
                name="base",
                version=TemplateVersion(1, 0, 0),
                description="Base",
                author="test",
                created_at=datetime.now()
            ),
            content={}
        )
        registry.register(base)

        # Require newer version
        template = VersionedTemplate(
            metadata=TemplateMetadata(
                name="vm",
                version=TemplateVersion(1, 0, 0),
                description="VM",
                author="test",
                created_at=datetime.now(),
                dependencies={"base": ">=2.0.0"}  # Version conflict
            ),
            content={}
        )

        resolver = TemplateResolver(registry)

        with pytest.raises(ValueError, match="Version conflict"):
            resolver.resolve_dependencies(template)

    def test_resolve_transitive_dependencies(self):
        """Test resolving transitive (nested) dependencies."""
        from azlin.templates.composition import TemplateResolver
        from azlin.templates.marketplace import TemplateRegistry
        from azlin.templates.versioning import VersionedTemplate, TemplateMetadata, TemplateVersion

        registry = TemplateRegistry()

        # A depends on nothing
        template_a = VersionedTemplate(
            metadata=TemplateMetadata(
                name="a",
                version=TemplateVersion(1, 0, 0),
                description="A",
                author="test",
                created_at=datetime.now()
            ),
            content={"resources": [{"type": "a"}]}
        )

        # B depends on A
        template_b = VersionedTemplate(
            metadata=TemplateMetadata(
                name="b",
                version=TemplateVersion(1, 0, 0),
                description="B",
                author="test",
                created_at=datetime.now(),
                dependencies={"a": ">=1.0.0"}
            ),
            content={"resources": [{"type": "b"}]}
        )

        # C depends on B (and transitively on A)
        template_c = VersionedTemplate(
            metadata=TemplateMetadata(
                name="c",
                version=TemplateVersion(1, 0, 0),
                description="C",
                author="test",
                created_at=datetime.now(),
                dependencies={"b": ">=1.0.0"}
            ),
            content={"resources": [{"type": "c"}]}
        )

        registry.register(template_a)
        registry.register(template_b)

        resolver = TemplateResolver(registry)
        resolved = resolver.resolve_dependencies(template_c)

        # Should have resources from A, B, and C
        resource_types = [r["type"] for r in resolved.content["resources"]]
        assert "a" in resource_types
        assert "b" in resource_types
        assert "c" in resource_types
