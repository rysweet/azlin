"""Error analyzer for Azure CLI error messages.

This module parses Azure CLI errors and provides actionable suggestions.

Philosophy:
- Ruthless simplicity: Pattern matching, no AI
- Clear contract: analyze() takes error, returns enhanced message
- Self-contained: All error patterns in one module

Public API (the "studs"):
    ErrorAnalyzer: Main class for analyzing errors
"""

import re

__all__ = ["ErrorAnalyzer"]


class ErrorAnalyzer:
    """Analyze Azure CLI errors and suggest fixes.

    Uses pattern matching to identify common Azure errors and provide
    actionable suggestions to users.

    Example:
        >>> analyzer = ErrorAnalyzer()
        >>> error = "ResourceGroupNotFound: Resource group 'my-rg' not found"
        >>> enhanced = analyzer.analyze("azlin new --name test", error)
        >>> print(enhanced)
        Resource group 'my-rg' not found.
        Suggestion: Try setting resource group with: azlin config set-rg <name>
    """

    # Error patterns with suggestions
    # Format: (regex_pattern, suggestion_template)
    ERROR_PATTERNS = [
        # Authentication errors
        (
            r"AuthenticationFailed|Please run 'az login'",
            "Authentication failed.\nSuggestion: Run 'az login' to authenticate with Azure",
        ),
        (
            r"SubscriptionNotFound|subscription.*not found",
            "Subscription not found.\nSuggestion: Check your subscription with 'az account list'",
        ),
        # Resource group errors
        (
            r"ResourceGroupNotFound|resource group.*not found",
            "Resource group not found.\nSuggestion: Create resource group or set existing one with 'azlin config set-rg <name>'",
        ),
        # VM errors
        (
            r"VMNotFound|virtual machine.*not found",
            "VM not found.\nSuggestion: List available VMs with 'azlin list'",
        ),
        (
            r"VMAlreadyExists|virtual machine.*already exists",
            "VM with this name already exists.\nSuggestion: Choose a different name or delete existing VM with 'azlin kill <vm-name>'",
        ),
        (
            r"VMNotRunning|VM is not running",
            "VM is not running.\nSuggestion: Start the VM with 'azlin start <vm-name>'",
        ),
        # Quota and capacity errors
        (
            r"QuotaExceeded|quota.*exceeded",
            "Quota exceeded in this region.\nSuggestion: Try a different region or VM size, or request quota increase",
        ),
        (
            r"SkuNotAvailable|SKU.*not available",
            "VM size not available in this region.\nSuggestion: Try a different VM size or region",
        ),
        (
            r"OperationNotAllowed.*zone",
            "Availability zone not supported.\nSuggestion: Remove zone specification or try a different region",
        ),
        # Network errors
        (
            r"NetworkSecurityGroupNotFound",
            "Network security group not found.\nSuggestion: Check network configuration or recreate VM",
        ),
        (
            r"PublicIPAddressCannotBeDeleted",
            "Public IP address is in use.\nSuggestion: Deallocate or delete associated VM first",
        ),
        (
            r"SubnetNotFound",
            "Subnet not found.\nSuggestion: Check virtual network configuration",
        ),
        # Storage errors
        (
            r"StorageAccountNotFound|storage account.*not found",
            "Storage account not found.\nSuggestion: Create storage account with 'azlin storage create <name>'",
        ),
        (
            r"StorageAccountAlreadyExists",
            "Storage account name already taken (must be globally unique).\nSuggestion: Try a different storage account name",
        ),
        # Bastion errors
        (
            r"BastionNotFound|bastion.*not found",
            "Azure Bastion not configured for this VNet.\nSuggestion: azlin will create Bastion automatically if needed, or configure manually",
        ),
        # Permission errors
        (
            r"AuthorizationFailed|not authorized",
            "Authorization failed - insufficient permissions.\nSuggestion: Check your Azure role assignments or contact subscription admin",
        ),
        (
            r"RoleAssignmentNotFound",
            "Role assignment not found.\nSuggestion: Verify your permissions with subscription admin",
        ),
        # Configuration errors
        (
            r"InvalidParameter|invalid.*parameter",
            "Invalid parameter in command.\nSuggestion: Check command syntax with 'azlin <command> --help'",
        ),
        (
            r"MissingParameter|parameter.*required",
            "Required parameter missing.\nSuggestion: Check command syntax with 'azlin <command> --help'",
        ),
        # Timeout errors
        (
            r"OperationTimedOut|operation.*timed out",
            "Operation timed out.\nSuggestion: Try again - Azure may be experiencing delays",
        ),
        # Key Vault errors
        (
            r"KeyVaultNotFound|key vault.*not found",
            "Key Vault not found.\nSuggestion: Check Key Vault configuration or permissions",
        ),
        # Resource not found (generic)
        (
            r"ResourceNotFound",
            "Resource not found.\nSuggestion: Verify resource name and check with 'azlin list'",
        ),
    ]

    def analyze(self, command: str, stderr: str) -> str:
        """Analyze error and return enhanced message with suggestions.

        Args:
            command: The azlin command that failed
            stderr: Error output from command

        Returns:
            Enhanced error message with actionable suggestions

        Example:
            >>> analyzer = ErrorAnalyzer()
            >>> error = "ResourceGroupNotFound: RG not found"
            >>> enhanced = analyzer.analyze("azlin new --name test", error)
            >>> "Suggestion:" in enhanced
            True
        """
        if not stderr or not stderr.strip():
            return "Command failed with no error message"

        # Try to match error patterns
        for pattern, suggestion in self.ERROR_PATTERNS:
            if re.search(pattern, stderr, re.IGNORECASE):
                # Extract key information from error if possible
                enhanced_msg = self._extract_error_details(stderr)
                return f"{enhanced_msg}\n{suggestion}"

        # No pattern matched - return original error with generic suggestion
        return f"{stderr.strip()}\n\nSuggestion: Check the error message above and verify your command syntax with 'azlin <command> --help'"

    def _extract_error_details(self, stderr: str) -> str:
        """Extract key details from error message.

        Args:
            stderr: Raw error output

        Returns:
            Cleaned error message with key details

        Example:
            >>> analyzer = ErrorAnalyzer()
            >>> stderr = "ERROR: (ResourceGroupNotFound) Resource group 'test' not found\\nCode: ResourceGroupNotFound"
            >>> analyzer._extract_error_details(stderr)
            "Resource group 'test' not found"
        """
        # Try to extract the main error message (before "Code:" or stacktrace)
        lines = stderr.strip().split("\n")

        # Look for the first substantial line
        for line in lines:
            line = line.strip()
            # Skip empty lines
            if not line:
                continue
            # Skip lines starting with common prefixes
            if line.startswith("ERROR:"):
                # Remove "ERROR:" prefix and continue processing
                line = line[6:].strip()
            # Skip Traceback lines and Code: lines
            if (
                line.startswith("Traceback")
                or line.startswith("Code:")
                or line.startswith("Message:")
            ):
                continue
            # Skip file references from tracebacks
            if line.startswith("File "):
                continue
            # Remove error code in parentheses at start
            line = re.sub(r"^\((.*?)\)\s*", "", line)
            # If we have a substantial message, return it
            if len(line) > 10:
                return line

        # Fallback: return first non-empty line
        for line in lines:
            line_stripped = line.strip()
            if (
                line_stripped
                and not line_stripped.startswith("Code:")
                and not line_stripped.startswith("Message:")
            ):
                return line_stripped

        return stderr.strip()
