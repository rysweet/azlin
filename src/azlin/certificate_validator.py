"""Certificate validation module for service principal authentication.

This module provides certificate validation functionality including:
- Permission validation (0600 or 0400 only)
- Certificate format validation (PEM)
- Certificate expiration checking
- Certificate parsing and metadata extraction

Security:
- Enforces strict file permissions (P0-SEC-003)
- Validates certificate expiration with warnings (P0-SEC-004)
- Fail-fast on security violations
- No external command execution
"""

import stat
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from cryptography import x509

try:
    from cryptography import x509 as _x509
    from cryptography.hazmat.backends import default_backend as _default_backend
    from cryptography.hazmat.primitives import hashes as _hashes

    x509 = _x509
    default_backend = _default_backend
    hashes = _hashes
except ImportError:
    x509 = None  # Handle gracefully if cryptography not installed
    default_backend = None  # type: ignore[assignment]
    hashes = None  # type: ignore[assignment]


@dataclass
class CertificateValidation:
    """Certificate validation result."""

    valid: bool
    warnings: list[str]
    errors: list[str]
    expiration_status: str  # "valid", "expiring_soon", "expired", "unknown"
    expiration_date: datetime | None = None


@dataclass
class CertificateInfo:
    """Certificate metadata information."""

    path: str
    thumbprint: str | None
    expiration_date: datetime | None
    validation_status: str


class CertificateValidator:
    """Validator for certificate files used in service principal authentication.

    Security Controls:
    - SEC-003: Certificate permissions must be 0600 or 0400
    - SEC-004: Certificate expiration warnings (<30 days)

    This validator performs strict security checks and fails fast on violations.
    """

    ALLOWED_PERMISSIONS = (0o600, 0o400)  # Owner read-only or owner read-write
    EXPIRATION_WARNING_DAYS = 30

    @staticmethod
    def validate_certificate(cert_path: str | Path) -> CertificateValidation:
        """Validate certificate file for authentication use.

        Performs comprehensive validation:
        1. File existence check
        2. Permission validation (0600 or 0400 only)
        3. Format validation (PEM)
        4. Expiration check (with <30 day warnings)

        Args:
            cert_path: Path to certificate file

        Returns:
            CertificateValidation: Structured validation result

        Raises:
            No exceptions - all errors returned in result structure
        """
        cert_path = Path(cert_path)
        warnings = []
        errors = []

        # Check file existence
        if not cert_path.exists():
            errors.append(f"Certificate file not found: {cert_path}")
            return CertificateValidation(
                valid=False, warnings=warnings, errors=errors, expiration_status="unknown"
            )

        # Check permissions
        perms_valid, perm_warnings, perm_errors = CertificateValidator.check_permissions(cert_path)
        warnings.extend(perm_warnings)
        errors.extend(perm_errors)

        if not perms_valid:
            return CertificateValidation(
                valid=False, warnings=warnings, errors=errors, expiration_status="unknown"
            )

        # Parse certificate and validate format
        cert = CertificateValidator.parse_certificate(cert_path)
        if cert is None:
            errors.append("Invalid certificate format. Expected PEM format.")
            return CertificateValidation(
                valid=False, warnings=warnings, errors=errors, expiration_status="unknown"
            )

        # Check expiration
        expiration_status, exp_warnings = CertificateValidator.check_expiration(cert_path)
        warnings.extend(exp_warnings)

        # Extract expiration date if certificate was parsed
        expiration_date = None
        if cert:
            try:
                expiration_date = cert.not_valid_after_utc
            except AttributeError:
                # Older cryptography versions use not_valid_after
                expiration_date = cert.not_valid_after
                if expiration_date.tzinfo is None:
                    expiration_date = expiration_date.replace(tzinfo=UTC)

        # Determine overall validity
        is_valid = len(errors) == 0 and expiration_status != "expired"

        return CertificateValidation(
            valid=is_valid,
            warnings=warnings,
            errors=errors,
            expiration_status=expiration_status,
            expiration_date=expiration_date,
        )

    @staticmethod
    def check_permissions(cert_path: Path) -> tuple[bool, list[str], list[str]]:
        """Check certificate file permissions.

        Security requirement SEC-003: Certificate files must have permissions
        0600 (owner read-write) or 0400 (owner read-only).

        Args:
            cert_path: Path to certificate file

        Returns:
            Tuple of (is_valid, warnings, errors)
        """
        warnings = []
        errors = []

        if not cert_path.exists():
            errors.append(f"Certificate file not found: {cert_path}")
            return False, warnings, errors

        stat_info = cert_path.stat()
        mode = stat.S_IMODE(stat_info.st_mode)

        # Check if permissions are exactly 0600 or 0400
        if mode not in CertificateValidator.ALLOWED_PERMISSIONS:
            errors.append(
                f"Certificate has insecure permissions {oct(mode)}. "
                f"Must be 0600 or 0400 for security. "
                f"Fix with: chmod 600 {cert_path}"
            )
            return False, warnings, errors

        return True, warnings, errors

    @staticmethod
    def check_expiration(cert_path: Path) -> tuple[str, list[str]]:
        """Check certificate expiration.

        Security requirement SEC-004: Warn if certificate expires within 30 days.

        Args:
            cert_path: Path to certificate file

        Returns:
            Tuple of (status, warnings) where status is:
            - "valid": Certificate is valid and not expiring soon
            - "expiring_soon": Certificate expires within 30 days
            - "expired": Certificate has expired
            - "unknown": Could not determine expiration
        """
        warnings = []

        cert = CertificateValidator.parse_certificate(cert_path)
        if cert is None:
            return "unknown", warnings

        try:
            # Try newer cryptography API first
            try:
                expiration = cert.not_valid_after_utc
            except AttributeError:
                # Fall back to older API
                expiration = cert.not_valid_after
                # Ensure timezone aware
                if expiration.tzinfo is None:
                    expiration = expiration.replace(tzinfo=UTC)

            now = datetime.now(UTC)

            # Check if expired
            if expiration < now:
                return "expired", warnings

            # Check if expiring soon
            days_until_expiration = (expiration - now).days
            if days_until_expiration < CertificateValidator.EXPIRATION_WARNING_DAYS:
                warnings.append(
                    f"Certificate expires in {days_until_expiration} days on {expiration.date()}"
                )
                return "expiring_soon", warnings

            return "valid", warnings

        except Exception:
            # If we can't determine expiration, return unknown
            return "unknown", warnings

    @staticmethod
    def parse_certificate(cert_path: Path) -> Any:
        """Parse PEM certificate file.

        Args:
            cert_path: Path to certificate file

        Returns:
            Certificate object or None if parsing fails (x509.Certificate | None)
        """
        if x509 is None or default_backend is None:
            # cryptography library not available
            return None

        try:
            with open(cert_path, "rb") as f:
                cert_data = f.read()

            # Try to parse as PEM
            cert = x509.load_pem_x509_certificate(cert_data, default_backend())
            return cert

        except Exception:
            # Could not parse certificate
            return None

    @staticmethod
    def get_certificate_info(cert_path: str | Path) -> CertificateInfo:
        """Get certificate metadata information.

        Args:
            cert_path: Path to certificate file

        Returns:
            CertificateInfo: Certificate metadata
        """
        cert_path = Path(cert_path)

        # Parse certificate
        cert = CertificateValidator.parse_certificate(cert_path)

        # Extract thumbprint (SHA-256 fingerprint)
        thumbprint = None
        expiration_date = None
        validation_status = "unknown"

        if cert and hashes is not None:
            try:
                # Calculate SHA-256 fingerprint
                fingerprint = cert.fingerprint(hashes.SHA256())
                thumbprint = fingerprint.hex().upper()

                # Extract expiration
                try:
                    expiration_date = cert.not_valid_after_utc
                except AttributeError:
                    expiration_date = cert.not_valid_after
                    if expiration_date.tzinfo is None:
                        expiration_date = expiration_date.replace(tzinfo=UTC)

                # Determine validation status
                validation = CertificateValidator.validate_certificate(cert_path)
                if validation.valid:
                    validation_status = "valid"
                elif validation.expiration_status == "expired":
                    validation_status = "expired"
                elif validation.expiration_status == "expiring_soon":
                    validation_status = "expiring_soon"
                elif validation.errors:
                    validation_status = "invalid"

            except Exception:
                pass

        return CertificateInfo(
            path=str(cert_path),
            thumbprint=thumbprint,
            expiration_date=expiration_date,
            validation_status=validation_status,
        )
