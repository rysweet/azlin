"""Unit tests for azdoit templates module."""

from azlin.azdoit.templates import OBJECTIVE_TEMPLATE, format_objective_prompt


class TestObjectiveTemplate:
    """Test the OBJECTIVE_TEMPLATE constant."""

    def test_template_has_required_sections(self):
        """Test that template contains all required sections."""
        assert "OBJECTIVE:" in OBJECTIVE_TEMPLATE
        assert "CONTEXT:" in OBJECTIVE_TEMPLATE
        assert "REQUIREMENTS:" in OBJECTIVE_TEMPLATE
        assert "LEARNING RESOURCES:" in OBJECTIVE_TEMPLATE
        assert "OUTPUT FORMAT:" in OBJECTIVE_TEMPLATE
        assert "EXECUTION STYLE:" in OBJECTIVE_TEMPLATE

    def test_template_has_user_request_placeholder(self):
        """Test that template has placeholder for user request."""
        assert "{user_request}" in OBJECTIVE_TEMPLATE

    def test_template_mentions_azure(self):
        """Test that template references Azure infrastructure."""
        assert "Azure" in OBJECTIVE_TEMPLATE or "azure" in OBJECTIVE_TEMPLATE.lower()


class TestFormatObjectivePrompt:
    """Test the format_objective_prompt function."""

    def test_format_simple_request(self):
        """Test formatting with a simple user request."""
        request = "create 3 VMs"
        result = format_objective_prompt(request)

        assert "OBJECTIVE: create 3 VMs" in result
        assert "CONTEXT:" in result
        assert "REQUIREMENTS:" in result

    def test_format_with_special_characters(self):
        """Test formatting with special characters in request."""
        request = 'create VM "test-1" with size Standard_D2s_v3'
        result = format_objective_prompt(request)

        assert 'OBJECTIVE: create VM "test-1" with size Standard_D2s_v3' in result
        assert "{user_request}" not in result

    def test_format_with_newlines(self):
        """Test formatting with newlines in request."""
        request = "create VM\nwith monitoring\nand backup"
        result = format_objective_prompt(request)

        assert "create VM" in result
        assert "with monitoring" in result
        assert "and backup" in result

    def test_format_simple_objective(self):
        """Test formatting with simple objective."""
        request = "provision AKS cluster"
        result = format_objective_prompt(request)

        assert "OBJECTIVE: provision AKS cluster" in result
        assert "REQUIREMENTS:" in result

    def test_format_preserves_template_structure(self):
        """Test that formatting preserves all template sections."""
        request = "test request"
        result = format_objective_prompt(request)

        # All sections should be present
        assert "OBJECTIVE:" in result
        assert "CONTEXT:" in result
        assert "REQUIREMENTS:" in result
        assert "LEARNING RESOURCES:" in result
        assert "OUTPUT FORMAT:" in result
        assert "EXECUTION STYLE:" in result

    def test_format_complex_request(self):
        """Test formatting with complex multi-part request."""
        request = "create resource group, storage account, and configure networking"
        result = format_objective_prompt(request)

        assert f"OBJECTIVE: {request}" in result
        assert "Azure" in result
