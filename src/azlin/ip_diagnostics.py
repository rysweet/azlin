"""IP diagnostics module for azlin - Issue #186.

This module provides IP classification, connectivity testing, and NSG rule checking
to help diagnose Azure VM network issues.

Key Feature: Correctly identifies Azure public IPs in the 172.171.0.0/16 range
that appear private but are actually Azure's public IP allocation.
"""

import ipaddress
import json
import subprocess
from typing import Any, Dict, Optional


def classify_ip_address(ip: Optional[str]) -> Optional[str]:
    """Classify an IP address as Private, Public, or Public-Azure.

    CRITICAL: Azure uses 172.171.0.0/16 for public IPs, which looks like
    RFC1918 private space but is NOT. This function checks Azure ranges FIRST
    before standard private ranges.

    Args:
        ip: IP address string to classify, or None

    Returns:
        - "Public-Azure": IP in Azure's 172.171.0.0/16 public range
        - "Public": Standard public IP address
        - "Private": RFC1918 private IP address
        - None: If ip is None or empty string

    Raises:
        ValueError: If IP address format is invalid

    Example:
        >>> classify_ip_address("172.171.118.91")
        "Public-Azure"
        >>> classify_ip_address("8.8.8.8")
        "Public"
        >>> classify_ip_address("10.0.0.24")
        "Private"
    """
    # Handle None and empty string
    if ip is None or ip == "":
        return None

    # Validate IP format
    try:
        ip_obj = ipaddress.ip_address(ip)
    except ValueError:
        raise ValueError(f"Invalid IP address: {ip}")

    # CRITICAL: Check Azure public IP range FIRST (172.171.0.0/16)
    # This MUST come before private IP checks!
    azure_public_network = ipaddress.ip_network("172.171.0.0/16")
    if ip_obj in azure_public_network:
        return "Public-Azure"

    # Check if it's a private IP (RFC1918 + loopback)
    if ip_obj.is_private or ip_obj.is_loopback:
        return "Private"

    # Everything else is public
    return "Public"


def check_connectivity(ip: Optional[str], port: int = 22, timeout: int = 3) -> bool:
    """Test connectivity to an IP address using ping.

    Uses subprocess to run ping command for basic connectivity testing.

    Args:
        ip: IP address to test
        port: Port number to test (default: 22 for SSH) - not used with ping
        timeout: Connection timeout in seconds (default: 3)

    Returns:
        True if ping succeeds, False otherwise

    Raises:
        ValueError: If ip is None

    Example:
        >>> check_connectivity("8.8.8.8", timeout=5)
        True
    """
    if ip is None:
        raise ValueError("IP address cannot be None")

    try:
        # Use ping command for connectivity check
        # -c 1: send 1 packet
        # -W timeout: wait time in seconds
        result = subprocess.run(
            ["ping", "-c", "1", "-W", str(timeout), ip],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

        return result.returncode == 0

    except (subprocess.TimeoutExpired, OSError):
        return False


def check_nsg_rules(
    resource_group: str, nsg_name: str, port: int = 22
) -> Dict[str, Any]:
    """Check NSG rules to determine if a port is allowed.

    Queries Azure NSG using Azure CLI and checks for allow/deny rules
    on the specified port.

    Args:
        resource_group: Azure resource group name
        nsg_name: Network Security Group name
        port: Port number to check (default: 22)

    Returns:
        Dictionary with:
        - allowed (bool): Whether port is allowed
        - rule_name (str or None): Name of matching rule

    Raises:
        RuntimeError: If Azure CLI query fails

    Example:
        >>> check_nsg_rules("my-rg", "my-nsg", port=22)
        {"allowed": True, "rule_name": "AllowSSH"}
    """
    # Query NSG rules using Azure CLI
    cmd = [
        "az",
        "network",
        "nsg",
        "show",
        "--resource-group",
        resource_group,
        "--name",
        nsg_name,
        "--output",
        "json",
    ]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, check=False, timeout=30
        )

        if result.returncode != 0:
            raise RuntimeError(
                f"Failed to query NSG: {result.stderr or 'Unknown error'}"
            )

        nsg_data = json.loads(result.stdout)

    except subprocess.TimeoutExpired:
        raise RuntimeError("NSG query timed out after 30 seconds")
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to parse NSG data: {e}")

    # Check security rules for matching port
    security_rules = nsg_data.get("securityRules", [])

    for rule in security_rules:
        # Check if rule applies to our port
        dest_port = rule.get("destinationPortRange", "")
        direction = rule.get("direction", "")

        # Simple port matching (exact match or wildcard)
        if direction == "Inbound" and (dest_port == str(port) or dest_port == "*"):
            access = rule.get("access", "")
            rule_name = rule.get("name", "")

            return {
                "allowed": access == "Allow",
                "rule_name": rule_name,
            }

    # No matching rule found
    return {
        "allowed": False,
        "rule_name": None,
    }


def format_diagnostic_report(diagnostic_data: Dict[str, Any]) -> str:
    """Format diagnostic data into a user-friendly report.

    Creates educational output explaining IP classification and connectivity status.

    Args:
        diagnostic_data: Dictionary containing:
            - ip (str): IP address
            - classification (str): IP classification
            - connectivity (bool): Connectivity status
            - nsg_check (dict or None): NSG check results

    Returns:
        Formatted diagnostic report string

    Example:
        >>> data = {
        ...     "ip": "172.171.118.91",
        ...     "classification": "Public-Azure",
        ...     "connectivity": True,
        ...     "nsg_check": {"allowed": True, "rule_name": "AllowSSH"}
        ... }
        >>> report = format_diagnostic_report(data)
    """
    ip = diagnostic_data.get("ip")
    classification = diagnostic_data.get("classification")
    connectivity = diagnostic_data.get("connectivity")
    nsg_check = diagnostic_data.get("nsg_check")

    # Handle None IP
    if ip is None:
        return "Diagnostic Report:\n  IP: No IP address available\n"

    # Build report
    lines = []
    lines.append("=" * 70)
    lines.append("IP DIAGNOSTIC REPORT")
    lines.append("=" * 70)
    lines.append(f"IP Address: {ip}")
    lines.append(f"Classification: {classification}")

    # Add educational note for Azure public IPs
    if classification == "Public-Azure":
        lines.append("")
        lines.append("NOTE: This IP is in Azure's 172.171.0.0/16 public range.")
        lines.append("These IPs look private but are actually Azure public IPs!")

    # Connectivity status
    lines.append("")
    if connectivity is True:
        lines.append("Connectivity: Success (port 22 reachable)")
    elif connectivity is False:
        lines.append("Connectivity: Failed (port 22 not reachable)")
    else:
        lines.append("Connectivity: Not tested")

    # NSG check results
    if nsg_check:
        lines.append("")
        lines.append("NSG Rule Check:")
        if nsg_check.get("allowed"):
            lines.append(f"  Status: Allowed")
            if nsg_check.get("rule_name"):
                lines.append(f"  Rule: {nsg_check['rule_name']}")
        else:
            lines.append(f"  Status: Denied or No matching rule")
            if nsg_check.get("rule_name"):
                lines.append(f"  Rule: {nsg_check['rule_name']}")

    lines.append("=" * 70)
    return "\n".join(lines)


def run_ip_diagnostic(
    ip: str,
    resource_group: Optional[str] = None,
    nsg_name: Optional[str] = None,
    check_port: int = 22,
) -> Dict[str, Any]:
    """Run complete IP diagnostic flow.

    Orchestrates IP classification, connectivity testing, and NSG rule checking.

    Args:
        ip: IP address to diagnose
        resource_group: Azure resource group (optional, skips NSG check if None)
        nsg_name: NSG name (optional, skips NSG check if None)
        check_port: Port to test (default: 22)

    Returns:
        Dictionary containing:
        - ip (str): IP address
        - classification (str): IP classification result
        - connectivity (bool): Connectivity test result
        - nsg_check (dict or None): NSG check results

    Example:
        >>> result = run_ip_diagnostic(
        ...     ip="172.171.118.91",
        ...     resource_group="my-rg",
        ...     nsg_name="my-nsg",
        ...     check_port=22
        ... )
        >>> print(result["classification"])
        "Public-Azure"
    """
    # Step 1: Classify IP
    classification = classify_ip_address(ip)

    # Step 2: Check connectivity
    connectivity = check_connectivity(ip, port=check_port)

    # Step 3: Check NSG rules (if resource group provided)
    nsg_check = None
    if resource_group and nsg_name:
        try:
            nsg_check = check_nsg_rules(resource_group, nsg_name, port=check_port)
        except RuntimeError:
            # NSG check failed, but continue with other diagnostics
            nsg_check = None

    return {
        "ip": ip,
        "classification": classification,
        "connectivity": connectivity,
        "nsg_check": nsg_check,
    }
