"""Compound VM:session identifier parsing and resolution.

Philosophy:
- Single responsibility: Parse and resolve compound identifiers
- Ruthlessly simple: ~100 lines, no external dependencies
- Standard library only
- Zero-BS: Every function works or doesn't exist

Public API:
    parse_identifier: Parse compound format into VM and session names
    resolve_to_vm: Resolve identifier to specific VM from list
    format_display: Format VM as compound identifier for display
    CompoundIdentifierError: Base error for identifier issues
    AmbiguousIdentifierError: Multiple matches found
"""

from pathlib import Path
from typing import Optional

from azlin.vm_manager import VMInfo

__all__ = [
    "parse_identifier",
    "resolve_to_vm",
    "format_display",
    "CompoundIdentifierError",
    "AmbiguousIdentifierError",
]


class CompoundIdentifierError(Exception):
    """Base exception for compound identifier errors."""

    pass


class AmbiguousIdentifierError(CompoundIdentifierError):
    """Raised when identifier matches multiple VMs."""

    pass


def parse_identifier(identifier: str) -> tuple[str | None, str | None]:
    """Parse compound identifier into VM and session components.

    Formats supported:
    - "vm-name" -> (vm-name, None)
    - "vm-name:session-name" -> (vm-name, session-name)
    - ":session-name" -> (None, session-name)

    Args:
        identifier: String to parse (whitespace is trimmed)

    Returns:
        Tuple of (vm_name, session_name), either can be None

    Raises:
        CompoundIdentifierError: If format is invalid
    """
    # Trim whitespace
    identifier = identifier.strip()

    # Check empty
    if not identifier:
        raise CompoundIdentifierError("Identifier cannot be empty")

    # Check multiple colons
    if identifier.count(":") > 1:
        raise CompoundIdentifierError(
            f"Invalid identifier '{identifier}': multiple colons not allowed"
        )

    # No colon - simple identifier
    if ":" not in identifier:
        return (identifier, None)

    # Split on colon
    vm_part, session_part = identifier.split(":", 1)

    # Trim parts
    vm_part = vm_part.strip()
    session_part = session_part.strip()

    # Check for colon-only (":")
    if not vm_part and not session_part:
        raise CompoundIdentifierError("Identifier cannot be empty")

    # Return parsed components
    # Empty vm_part becomes None (session-only format: ":session")
    # Empty session_part is allowed (VM-only format: "vm:")
    return (vm_part if vm_part else None, session_part if session_part else None)


def resolve_to_vm(
    identifier: str, vms: list[VMInfo], config_path: str | None = None
) -> VMInfo:
    """Resolve identifier to specific VM from list.

    Resolution order:
    1. Parse identifier into vm_name and session_name
    2. If compound format (vm:session), match exact VM name and session
    3. If simple format, search for:
       - Exact VM name match, OR
       - Exact session name match (if unique)
    4. Check config file for session mapping (if provided)

    Args:
        identifier: Identifier to resolve
        vms: List of available VMs
        config_path: Optional path to config file for session mapping

    Returns:
        Matching VMInfo

    Raises:
        CompoundIdentifierError: If no match found or format invalid
        AmbiguousIdentifierError: If multiple matches found
    """
    # Parse identifier
    vm_name, session_name = parse_identifier(identifier)

    # Try config file lookup first (if provided and file exists)
    if config_path and Path(config_path).exists():
        try:
            import tomli

            with open(config_path, "rb") as f:
                config = tomli.load(f)

            # Check for session mapping
            sessions = config.get("sessions", {})
            if identifier in sessions:
                target_vm_name = sessions[identifier].get("vm")
                if target_vm_name:
                    # Find VM by name
                    for vm in vms:
                        if vm.name == target_vm_name:
                            return vm
        except Exception as e:
            # Config file issues (malformed TOML, missing keys, import errors)
            # Fall back to VM list search since config lookup is optional
            # This preserves existing behavior while making errors visible
            import sys
            print(
                f"Warning: Config file lookup failed ({type(e).__name__}: {e}), "
                f"falling back to VM list search",
                file=sys.stderr,
            )

    # Compound format with VM name specified
    if vm_name is not None and ":" in identifier:
        # Find VM by exact name match
        matching_vm = next((vm for vm in vms if vm.name == vm_name), None)

        if not matching_vm:
            raise CompoundIdentifierError(
                f"VM '{vm_name}' not found. Available VMs: {', '.join(vm.name for vm in vms)}"
            )

        # If session_name is specified, verify it matches
        if session_name is not None:
            if not matching_vm.session_name:
                raise CompoundIdentifierError(
                    f"VM '{vm_name}' has no session name (cannot match '{session_name}')"
                )

            if matching_vm.session_name != session_name:
                raise CompoundIdentifierError(
                    f"VM '{vm_name}' session name mismatch: expected '{session_name}', actual '{matching_vm.session_name}'"
                )

        return matching_vm

    # Session-only format (:session)
    if vm_name is None and session_name is not None:
        matches = [vm for vm in vms if vm.session_name == session_name]

        if not matches:
            raise CompoundIdentifierError(
                f"Session '{session_name}' not found. Available sessions: {', '.join(vm.session_name or vm.name for vm in vms if vm.session_name)}"
            )

        if len(matches) > 1:
            suggestions = "\n".join(
                f"  - {format_display(vm)} ({vm.public_ip or 'no IP'})"
                for vm in matches
            )
            raise AmbiguousIdentifierError(
                f"Multiple VMs found with session '{session_name}':\n{suggestions}\n\nUse compound format to specify: <vm-name>:{session_name}"
            )

        return matches[0]

    # Simple format (no colon)
    # Search for VM name or session name
    vm_matches = [vm for vm in vms if vm.name == identifier]
    session_matches = [vm for vm in vms if vm.session_name == identifier]

    # Exact VM name match
    if len(vm_matches) == 1 and len(session_matches) == 0:
        return vm_matches[0]

    # Exact session name match
    if len(session_matches) == 1 and len(vm_matches) == 0:
        return session_matches[0]

    # Ambiguous - both VM and session match
    if len(vm_matches) > 0 and len(session_matches) > 0:
        all_matches = vm_matches + session_matches
        suggestions = "\n".join(
            f"  - {format_display(vm)} ({vm.public_ip or 'no IP'})"
            for vm in all_matches
        )
        raise AmbiguousIdentifierError(
            f"Multiple VMs match '{identifier}':\n{suggestions}\n\nUse compound format to specify which one"
        )

    # Multiple session matches
    if len(session_matches) > 1:
        suggestions = "\n".join(
            f"  - {format_display(vm)} ({vm.public_ip or 'no IP'})"
            for vm in session_matches
        )
        raise AmbiguousIdentifierError(
            f"Multiple VMs found with session '{identifier}':\n{suggestions}\n\nUse compound format to specify: <vm-name>:{identifier}"
        )

    # No matches
    available = ", ".join(
        format_display(vm) for vm in vms if vm.session_name or vm.name
    )
    raise CompoundIdentifierError(
        f"VM or session '{identifier}' not found. Available: {available}"
    )


def format_display(vm: VMInfo) -> str:
    """Format VM as compound identifier for display.

    Args:
        vm: VM to format

    Returns:
        Formatted string (vm-name:session or just vm-name)
    """
    if vm.session_name and vm.session_name.strip():
        return f"{vm.name}:{vm.session_name}"
    return vm.name
