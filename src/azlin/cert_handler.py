"""Certificate handler for Azure Service Principal authentication.

This module provides certificate validation, permissions checks, and expiration monitoring
following strict security requirements (P0 controls).

Security Requirements:
- Only 0600 or 0400 file permissions are allowed
- Certificates must be in valid PEM format
- Expiration checks with warning if <30 days
- Fail fast on any validation errors
"""

import os
import stat
from dataclasses import dataclass
from datetime import UTC, datetime

from cryptography import x509
from cryptography.hazmat.backends import default_backend


@dataclass
class CertValidation:
    """Certificate validation result.

    Attributes:
        valid: True if certificate passes all validation checks
        cert_path: Path to the certificate file
        permissions: Unix file permissions (octal)
        expiration_date: Certificate expiration date
        days_until_expiry: Days until certificate expires (negative if expired)
        errors: List of validation errors
        warnings: List of validation warnings
    """

    valid: bool
    cert_path: str
    permissions: int
    expiration_date: datetime | None
    days_until_expiry: int | None
    errors: list[str]
    warnings: list[str]


@dataclass
class ExpirationStatus:
    """Certificate expiration status.

    Attributes:
        cert_path: Path to the certificate file
        expiration_date: Certificate expiration date
        days_until_expiry: Days until certificate expires (negative if expired)
        is_expired: True if certificate has expired
        needs_warning: True if certificate expires within 30 days
    """

    cert_path: str
    expiration_date: datetime
    days_until_expiry: int
    is_expired: bool
    needs_warning: bool


# P0 Security Control: Only these permissions are allowed
ALLOWED_PERMISSIONS = {0o600, 0o400}
EXPIRATION_WARNING_DAYS = 30


def validate_certificate(cert_path: str) -> CertValidation:
    """Validate certificate file and permissions.

    Performs comprehensive validation including:
    - File existence and readability
    - Permissions check (must be exactly 0600 or 0400)
    - PEM format validation
    - Certificate expiration check

    Args:
        cert_path: Path to certificate file

    Returns:
        CertValidation object with validation results
    """
    errors: list[str] = []
    warnings: list[str] = []
    permissions = 0
    expiration_date = None
    days_until_expiry = None

    # Check file exists
    if not os.path.exists(cert_path):
        errors.append(f"Certificate file not found: {cert_path}")
        return CertValidation(
            valid=False,
            cert_path=cert_path,
            permissions=permissions,
            expiration_date=expiration_date,
            days_until_expiry=days_until_expiry,
            errors=errors,
            warnings=warnings,
        )

    # Check file is readable
    if not os.access(cert_path, os.R_OK):
        errors.append(f"Certificate file is not readable: {cert_path}")

    # Check permissions (P0 requirement)
    try:
        file_stat = os.stat(cert_path)
        permissions = stat.S_IMODE(file_stat.st_mode)

        if permissions not in ALLOWED_PERMISSIONS:
            errors.append(
                f"Invalid certificate permissions: {oct(permissions)}. "
                f"Must be exactly 0600 or 0400 for security."
            )
    except OSError as e:
        errors.append(f"Failed to check file permissions: {e}")

    # If we can't read the file or permissions are wrong, stop here
    if errors:
        return CertValidation(
            valid=False,
            cert_path=cert_path,
            permissions=permissions,
            expiration_date=expiration_date,
            days_until_expiry=days_until_expiry,
            errors=errors,
            warnings=warnings,
        )

    # Validate PEM format and parse certificate
    try:
        with open(cert_path, "rb") as f:
            cert_data = f.read()

        # Parse the certificate
        cert = x509.load_pem_x509_certificate(cert_data, default_backend())

        # Extract expiration information
        expiration_date = cert.not_valid_after_utc

        # Calculate days until expiry
        now = datetime.now(UTC)
        time_delta = expiration_date - now
        days_until_expiry = time_delta.days

        # Check if expired
        if days_until_expiry < 0:
            warnings.append(f"Certificate has expired (expired {abs(days_until_expiry)} days ago)")
        elif days_until_expiry < EXPIRATION_WARNING_DAYS:
            warnings.append(
                f"Certificate expires soon (in {days_until_expiry} days). Renewal recommended."
            )

    except ValueError as e:
        errors.append(f"Invalid certificate format: {e}")
    except Exception as e:
        errors.append(f"Failed to parse certificate: {e}")

    # Determine if validation passed
    valid = len(errors) == 0

    return CertValidation(
        valid=valid,
        cert_path=cert_path,
        permissions=permissions,
        expiration_date=expiration_date,
        days_until_expiry=days_until_expiry,
        errors=errors,
        warnings=warnings,
    )


def check_expiration(cert_path: str) -> ExpirationStatus:
    """Check certificate expiration status.

    Args:
        cert_path: Path to certificate file

    Returns:
        ExpirationStatus with expiration details

    Raises:
        FileNotFoundError: If certificate file does not exist
        ValueError: If certificate format is invalid
        Exception: For other certificate parsing errors
    """
    if not os.path.exists(cert_path):
        raise FileNotFoundError(f"Certificate file not found: {cert_path}")

    # Read and parse certificate
    with open(cert_path, "rb") as f:
        cert_data = f.read()

    try:
        cert = x509.load_pem_x509_certificate(cert_data, default_backend())
    except ValueError as e:
        raise ValueError(f"Invalid certificate format: {e}") from e

    # Extract expiration information
    expiration_date = cert.not_valid_after_utc

    # Calculate days until expiry
    now = datetime.now(UTC)
    time_delta = expiration_date - now
    days_until_expiry = time_delta.days

    # Determine status flags
    is_expired = days_until_expiry < 0
    needs_warning = days_until_expiry < EXPIRATION_WARNING_DAYS

    return ExpirationStatus(
        cert_path=cert_path,
        expiration_date=expiration_date,
        days_until_expiry=days_until_expiry,
        is_expired=is_expired,
        needs_warning=needs_warning,
    )


def fix_certificate_permissions(cert_path: str) -> bool:
    """Fix certificate permissions to 0600.

    Only modifies permissions if they are incorrect. Will not change
    0400 permissions (which are also acceptable) to 0600.

    Args:
        cert_path: Path to certificate file

    Returns:
        True if permissions were fixed, False if already correct

    Raises:
        FileNotFoundError: If certificate file does not exist
        OSError: If unable to change permissions
    """
    if not os.path.exists(cert_path):
        raise FileNotFoundError(f"Certificate file not found: {cert_path}")

    # Check current permissions
    file_stat = os.stat(cert_path)
    current_perms = stat.S_IMODE(file_stat.st_mode)

    # If permissions are already correct, no change needed
    if current_perms in ALLOWED_PERMISSIONS:
        return False

    # Fix permissions to 0600 (read/write for owner only)
    os.chmod(cert_path, 0o600)
    return True
