"""Unit tests for template validation and linting.

Test coverage: Validation and linting (JSON Schema + Azure-specific)

These tests follow TDD - they should FAIL initially until implementation is complete.
"""



class TestJSONSchemaValidation:
    """Test JSON Schema validation for templates."""

    def test_validate_valid_template(self):
        """Test validating a well-formed template."""
        from azlin.templates.validation import TemplateValidator

        validator = TemplateValidator()

        template = {
            "metadata": {
                "name": "vm-basic",
                "version": "1.0.0",
                "description": "Basic VM template",
                "author": "test"
            },
            "content": {
                "resources": [
                    {"type": "Microsoft.Compute/virtualMachines", "name": "vm1"}
                ]
            }
        }

        result = validator.validate(template)

        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_validate_missing_required_field(self):
        """Test validation fails for missing required fields."""
        from azlin.templates.validation import TemplateValidator

        validator = TemplateValidator()

        template = {
            "metadata": {
                # Missing 'name' field
                "version": "1.0.0",
                "description": "Basic VM template"
            },
            "content": {}
        }

        result = validator.validate(template)

        assert result.is_valid is False
        assert any("name" in error.lower() for error in result.errors)

    def test_validate_invalid_version_format(self):
        """Test validation fails for invalid version format."""
        from azlin.templates.validation import TemplateValidator

        validator = TemplateValidator()

        template = {
            "metadata": {
                "name": "vm-basic",
                "version": "invalid",  # Invalid format
                "description": "Basic VM template",
                "author": "test"
            },
            "content": {}
        }

        result = validator.validate(template)

        assert result.is_valid is False
        assert any("version" in error.lower() for error in result.errors)

    def test_validate_invalid_type(self):
        """Test validation fails for wrong field types."""
        from azlin.templates.validation import TemplateValidator

        validator = TemplateValidator()

        template = {
            "metadata": {
                "name": "vm-basic",
                "version": "1.0.0",
                "description": 123,  # Should be string
                "author": "test"
            },
            "content": {}
        }

        result = validator.validate(template)

        assert result.is_valid is False
        assert any("description" in error.lower() for error in result.errors)

    def test_validate_nested_content_structure(self):
        """Test validation of nested content structure."""
        from azlin.templates.validation import TemplateValidator

        validator = TemplateValidator()

        template = {
            "metadata": {
                "name": "vm-basic",
                "version": "1.0.0",
                "description": "Basic VM",
                "author": "test"
            },
            "content": {
                "resources": "invalid"  # Should be array
            }
        }

        result = validator.validate(template)

        assert result.is_valid is False
        assert any("resources" in error.lower() for error in result.errors)

    def test_validate_with_warnings(self):
        """Test validation can return warnings for non-critical issues."""
        from azlin.templates.validation import TemplateValidator

        validator = TemplateValidator()

        template = {
            "metadata": {
                "name": "vm-basic",
                "version": "1.0.0",
                "description": "Basic VM",
                "author": "test"
                # Missing optional 'tags' field
            },
            "content": {
                "resources": []  # Empty resources (warning)
            }
        }

        result = validator.validate(template)

        assert result.is_valid is True  # Still valid
        assert len(result.warnings) > 0  # But has warnings


class TestAzureSpecificValidation:
    """Test Azure-specific validation rules."""

    def test_validate_azure_resource_type(self):
        """Test validation of Azure resource types."""
        from azlin.templates.validation import AzureValidator

        validator = AzureValidator()

        # Valid Azure resource type
        template = {
            "metadata": {"name": "test", "version": "1.0.0", "author": "test"},
            "content": {
                "resources": [
                    {"type": "Microsoft.Compute/virtualMachines", "name": "vm1"}
                ]
            }
        }

        result = validator.validate_azure_resources(template)
        assert result.is_valid is True

    def test_validate_invalid_azure_resource_type(self):
        """Test validation fails for invalid Azure resource types."""
        from azlin.templates.validation import AzureValidator

        validator = AzureValidator()

        template = {
            "metadata": {"name": "test", "version": "1.0.0", "author": "test"},
            "content": {
                "resources": [
                    {"type": "Invalid.Resource/Type", "name": "res1"}
                ]
            }
        }

        result = validator.validate_azure_resources(template)
        assert result.is_valid is False
        assert any("resource type" in error.lower() for error in result.errors)

    def test_validate_azure_location(self):
        """Test validation of Azure location values."""
        from azlin.templates.validation import AzureValidator

        validator = AzureValidator()

        # Valid location
        template = {
            "metadata": {"name": "test", "version": "1.0.0", "author": "test"},
            "content": {
                "parameters": {"location": "eastus"}
            }
        }

        result = validator.validate_azure_config(template)
        assert result.is_valid is True

    def test_validate_invalid_azure_location(self):
        """Test validation fails for invalid Azure locations."""
        from azlin.templates.validation import AzureValidator

        validator = AzureValidator()

        template = {
            "metadata": {"name": "test", "version": "1.0.0", "author": "test"},
            "content": {
                "parameters": {"location": "invalid-location"}
            }
        }

        result = validator.validate_azure_config(template)
        assert result.is_valid is False
        assert any("location" in error.lower() for error in result.errors)

    def test_validate_azure_vm_size(self):
        """Test validation of Azure VM sizes."""
        from azlin.templates.validation import AzureValidator

        validator = AzureValidator()

        # Valid VM size
        template = {
            "metadata": {"name": "test", "version": "1.0.0", "author": "test"},
            "content": {
                "parameters": {"vmSize": "Standard_D2s_v3"}
            }
        }

        result = validator.validate_azure_config(template)
        assert result.is_valid is True

    def test_validate_azure_naming_conventions(self):
        """Test validation of Azure naming conventions."""
        from azlin.templates.validation import AzureValidator

        validator = AzureValidator()

        # Invalid name (too long, invalid chars)
        template = {
            "metadata": {"name": "test", "version": "1.0.0", "author": "test"},
            "content": {
                "resources": [
                    {
                        "type": "Microsoft.Compute/virtualMachines",
                        "name": "invalid_name_with_underscores_and_way_too_long_for_azure_limits"
                    }
                ]
            }
        }

        result = validator.validate_azure_naming(template)
        assert result.is_valid is False
        assert any("naming" in error.lower() for error in result.errors)

    def test_validate_azure_sku_compatibility(self):
        """Test validation of Azure SKU compatibility."""
        from azlin.templates.validation import AzureValidator

        validator = AzureValidator()

        # Incompatible SKU combination
        template = {
            "metadata": {"name": "test", "version": "1.0.0", "author": "test"},
            "content": {
                "resources": [
                    {
                        "type": "Microsoft.Storage/storageAccounts",
                        "sku": {"name": "Premium_LRS"},
                        "kind": "BlobStorage"  # Incompatible with Premium
                    }
                ]
            }
        }

        result = validator.validate_azure_resources(template)
        assert result.is_valid is False
        assert any("sku" in error.lower() or "compatibility" in error.lower()
                   for error in result.errors)


class TestTemplateLinter:
    """Test template linting for style and best practices."""

    def test_lint_checks_resource_naming(self):
        """Test linter checks resource naming conventions."""
        from azlin.templates.validation import TemplateLinter

        linter = TemplateLinter()

        template = {
            "metadata": {"name": "test", "version": "1.0.0", "author": "test"},
            "content": {
                "resources": [
                    {"type": "Microsoft.Compute/virtualMachines", "name": "VM1"}  # Should be lowercase
                ]
            }
        }

        result = linter.lint(template)

        assert any("naming" in issue.lower() or "lowercase" in issue.lower()
                   for issue in result.issues)

    def test_lint_checks_missing_tags(self):
        """Test linter warns about missing tags."""
        from azlin.templates.validation import TemplateLinter

        linter = TemplateLinter()

        template = {
            "metadata": {"name": "test", "version": "1.0.0", "author": "test"},
            "content": {
                "resources": [
                    {
                        "type": "Microsoft.Compute/virtualMachines",
                        "name": "vm1"
                        # Missing tags
                    }
                ]
            }
        }

        result = linter.lint(template)

        assert any("tags" in issue.lower() for issue in result.issues)

    def test_lint_checks_description_quality(self):
        """Test linter checks description quality."""
        from azlin.templates.validation import TemplateLinter

        linter = TemplateLinter()

        # Too short description
        template = {
            "metadata": {
                "name": "test",
                "version": "1.0.0",
                "author": "test",
                "description": "VM"  # Too short
            },
            "content": {}
        }

        result = linter.lint(template)

        assert any("description" in issue.lower() for issue in result.issues)

    def test_lint_checks_parameter_defaults(self):
        """Test linter checks for missing parameter defaults."""
        from azlin.templates.validation import TemplateLinter

        linter = TemplateLinter()

        template = {
            "metadata": {"name": "test", "version": "1.0.0", "author": "test"},
            "content": {
                "parameters": {
                    "vmSize": {
                        "type": "string"
                        # Missing default value
                    }
                }
            }
        }

        result = linter.lint(template)

        assert any("default" in issue.lower() or "parameter" in issue.lower()
                   for issue in result.issues)

    def test_lint_checks_unused_variables(self):
        """Test linter detects unused variables."""
        from azlin.templates.validation import TemplateLinter

        linter = TemplateLinter()

        template = {
            "metadata": {"name": "test", "version": "1.0.0", "author": "test"},
            "content": {
                "variables": {
                    "unusedVar": "value"  # Not referenced anywhere
                },
                "resources": []
            }
        }

        result = linter.lint(template)

        assert any("unused" in issue.lower() for issue in result.issues)

    def test_lint_checks_security_best_practices(self):
        """Test linter checks security best practices."""
        from azlin.templates.validation import TemplateLinter

        linter = TemplateLinter()

        template = {
            "metadata": {"name": "test", "version": "1.0.0", "author": "test"},
            "content": {
                "parameters": {
                    "adminPassword": {
                        "type": "string",
                        "defaultValue": "Password123!"  # Hardcoded password
                    }
                }
            }
        }

        result = linter.lint(template)

        assert any("password" in issue.lower() or "security" in issue.lower()
                   for issue in result.issues)

    def test_lint_severity_levels(self):
        """Test linter assigns appropriate severity levels."""
        from azlin.templates.validation import TemplateLinter

        linter = TemplateLinter()

        template = {
            "metadata": {"name": "test", "version": "1.0.0", "author": "test"},
            "content": {
                "resources": [
                    {
                        "type": "Microsoft.Compute/virtualMachines",
                        "name": "vm1",
                        "properties": {
                            "osProfile": {
                                "adminPassword": "hardcoded"  # Critical
                            }
                        }
                    }
                ]
            }
        }

        result = linter.lint(template)

        # Should have at least one critical issue
        assert any(issue.severity == "critical" for issue in result.issues_detailed)


class TestValidationResult:
    """Test validation result objects."""

    def test_validation_result_creation(self):
        """Test creating validation result."""
        from azlin.templates.validation import ValidationResult

        result = ValidationResult(
            is_valid=True,
            errors=[],
            warnings=["Minor issue"]
        )

        assert result.is_valid is True
        assert len(result.errors) == 0
        assert len(result.warnings) == 1

    def test_validation_result_summary(self):
        """Test validation result summary generation."""
        from azlin.templates.validation import ValidationResult

        result = ValidationResult(
            is_valid=False,
            errors=["Error 1", "Error 2"],
            warnings=["Warning 1"]
        )

        summary = result.get_summary()

        assert "Error 1" in summary
        assert "Error 2" in summary
        assert "Warning 1" in summary
        assert "2" in summary  # Error count

    def test_validation_result_json_export(self):
        """Test exporting validation result to JSON."""
        from azlin.templates.validation import ValidationResult

        result = ValidationResult(
            is_valid=False,
            errors=["Error"],
            warnings=["Warning"]
        )

        json_data = result.to_json()

        assert "is_valid" in json_data
        assert json_data["is_valid"] is False
        assert "errors" in json_data
        assert "warnings" in json_data


class TestValidatorConfiguration:
    """Test validator configuration options."""

    def test_validator_with_custom_rules(self):
        """Test validator with custom validation rules."""
        from azlin.templates.validation import TemplateValidator

        def custom_rule(template):
            if "custom_field" not in template["metadata"]:
                return ["Missing custom_field"]
            return []

        validator = TemplateValidator(custom_rules=[custom_rule])

        template = {
            "metadata": {
                "name": "test",
                "version": "1.0.0",
                "author": "test"
                # Missing custom_field
            },
            "content": {}
        }

        result = validator.validate(template)

        assert any("custom_field" in error for error in result.errors)

    def test_validator_strict_mode(self):
        """Test validator in strict mode treats warnings as errors."""
        from azlin.templates.validation import TemplateValidator

        validator = TemplateValidator(strict=True)

        template = {
            "metadata": {
                "name": "test",
                "version": "1.0.0",
                "author": "test"
            },
            "content": {
                "resources": []  # Empty (normally warning)
            }
        }

        result = validator.validate(template)

        # In strict mode, warnings become errors
        assert result.is_valid is False

    def test_validator_disable_specific_checks(self):
        """Test disabling specific validation checks."""
        from azlin.templates.validation import TemplateValidator

        validator = TemplateValidator(disabled_checks=["naming-convention"])

        template = {
            "metadata": {"name": "test", "version": "1.0.0", "author": "test"},
            "content": {
                "resources": [
                    {"type": "Microsoft.Compute/virtualMachines", "name": "INVALID_NAME"}
                ]
            }
        }

        result = validator.validate(template)

        # Should not report naming issue since check is disabled
        assert not any("naming" in error.lower() for error in result.errors)
