"""Example usage of ProfileManager.

This script demonstrates how to use the ProfileManager to create, load,
list, update, and delete authentication profiles.
"""

from pathlib import Path

from azlin.config_auth import AuthConfig
from azlin.profile_manager import ProfileManager


# Example 1: Create a profile for service principal with certificate
def example_create_cert_profile():
    """Create a profile for certificate-based authentication."""
    manager = ProfileManager()

    # Create AuthConfig for service principal with certificate
    config = AuthConfig(
        auth_method="service_principal_cert",
        tenant_id="12345678-1234-1234-1234-123456789abc",
        client_id="87654321-4321-4321-4321-cba987654321",
        client_certificate_path="~/certs/production.pem",
        subscription_id="abcdef01-2345-6789-abcd-ef0123456789",
    )

    # Create profile
    info = manager.create_profile("production", config)
    print(f"Created profile: {info.name}")
    print(f"  Auth method: {info.auth_method}")
    print(f"  Tenant ID: {info.tenant_id}")
    print(f"  Created at: {info.created_at}")


# Example 2: Load a profile
def example_load_profile():
    """Load an existing profile."""
    manager = ProfileManager()

    # Load profile
    config = manager.get_profile("production")
    print(f"Loaded profile: {config.profile_name}")
    print(f"  Auth method: {config.auth_method}")
    print(f"  Tenant ID: {config.tenant_id}")
    print(f"  Certificate path: {config.client_certificate_path}")


# Example 3: List all profiles
def example_list_profiles():
    """List all available profiles."""
    manager = ProfileManager()

    profiles = manager.list_profiles()
    print(f"Found {len(profiles)} profiles:")
    for profile in profiles:
        print(f"  - {profile.name} ({profile.auth_method})")
        if profile.last_used:
            print(f"    Last used: {profile.last_used}")


# Example 4: Update last_used timestamp
def example_update_last_used():
    """Update the last_used timestamp for a profile."""
    manager = ProfileManager()

    # Update last_used
    manager.update_last_used("production")
    print("Updated last_used timestamp for production profile")


# Example 5: Delete a profile
def example_delete_profile():
    """Delete a profile."""
    manager = ProfileManager()

    # Delete profile
    deleted = manager.delete_profile("staging")
    if deleted:
        print("Deleted staging profile")
    else:
        print("Profile not found")


# Example 6: Create a simple az_cli profile
def example_create_simple_profile():
    """Create a simple profile using az_cli (default)."""
    manager = ProfileManager()

    # Create simple profile with just subscription ID
    config = AuthConfig(
        auth_method="az_cli",
        subscription_id="abcdef01-2345-6789-abcd-ef0123456789",
    )

    info = manager.create_profile("default", config)
    print(f"Created default profile: {info.name}")


# Example 7: Use custom profiles directory
def example_custom_directory():
    """Use a custom profiles directory."""
    custom_dir = Path.home() / "my-configs" / "profiles"
    manager = ProfileManager(profiles_dir=custom_dir)

    # Create profile in custom directory
    config = AuthConfig(auth_method="az_cli")
    info = manager.create_profile("custom", config)
    print(f"Created profile in custom directory: {custom_dir}")


# Example 8: Check if profile exists
def example_check_exists():
    """Check if a profile exists."""
    manager = ProfileManager()

    if manager.profile_exists("production"):
        print("Production profile exists")
    else:
        print("Production profile not found")


# Example 9: Security - profiles with secrets are rejected
def example_security_rejection():
    """Demonstrate that profiles with secrets are rejected."""
    manager = ProfileManager()

    try:
        # This will FAIL - client_secret cannot be stored in profiles
        config = AuthConfig(
            auth_method="service_principal_secret",
            tenant_id="12345678-1234-1234-1234-123456789abc",
            client_id="87654321-4321-4321-4321-cba987654321",
            client_secret="super-secret-value",  # FORBIDDEN
        )
        manager.create_profile("bad-profile", config)
    except Exception as e:
        print(f"Profile creation rejected (as expected): {type(e).__name__}")
        print("Secrets must be provided via environment variables, not stored in profiles")


if __name__ == "__main__":
    print("ProfileManager Examples")
    print("=" * 60)

    # Note: These examples are for documentation only.
    # Uncomment to run specific examples:

    # example_create_cert_profile()
    # example_load_profile()
    # example_list_profiles()
    # example_update_last_used()
    # example_delete_profile()
    # example_create_simple_profile()
    # example_custom_directory()
    # example_check_exists()
    # example_security_rejection()

    print("\nSee the function definitions for usage examples.")
