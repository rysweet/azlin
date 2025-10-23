"""Unit tests for auth_models module.

Tests the authentication data models defined in src/azlin/auth_models.py.
These tests verify:
- Enum properties and values
- Dataclass construction and validation
- UUID validation
- Immutability (frozen dataclasses)
- Secret masking
"""

import pytest
from datetime import datetime, timedelta
from pathlib import Path
import tempfile
import os

from azlin.auth_models import (
    AuthMethod,
    ServicePrincipalConfig,
    ManagedIdentityConfig,
    AuthConfig,
    AuthContext,
    ChainResult,
    CertificateInfo,
    CertificateValidation,
    validate_uuid,
)


class TestValidateUUID:
    """Test UUID validation helper function."""

    def test_valid_uuids(self):
        """Test that valid UUIDs are accepted."""
        valid_uuids = [
            "12345678-1234-1234-1234-123456789012",
            "87654321-4321-4321-4321-210987654321",
            "abcdef00-0000-0000-0000-000000abcdef",
            "ABCDEF00-0000-0000-0000-000000ABCDEF",
        ]
        for uuid in valid_uuids:
            validate_uuid(uuid, "test_field")

    def test_invalid_uuids(self):
        """Test that invalid UUIDs are rejected."""
        invalid_uuids = [
            "not-a-uuid",
            "12345678-1234-1234-1234",
            "12345678-1234-1234-1234-123456789012345",
            "",
            "XXXXXXXX-XXXX-XXXX-XXXX-XXXXXXXXXXXX",
            "12345678_1234_1234_1234_123456789012",
        ]
        for uuid in invalid_uuids:
            with pytest.raises(ValueError):
                validate_uuid(uuid, "test_field")

    def test_sql_injection_protection(self):
        """Test that UUID validation protects against SQL injection."""
        malicious = "12345678-1234-1234-1234-123456789012'; DROP TABLE users; --"
        with pytest.raises(ValueError):
            validate_uuid(malicious, "test_field")


class TestAuthMethod:
    """Test AuthMethod enumeration."""

    def test_enum_values(self):
        """Test that enum has correct values."""
        assert AuthMethod.AZURE_CLI.value == "azure_cli"
        assert AuthMethod.SERVICE_PRINCIPAL_SECRET.value == "sp_secret"
        assert AuthMethod.SERVICE_PRINCIPAL_CERTIFICATE.value == "sp_cert"
        assert AuthMethod.MANAGED_IDENTITY.value == "managed_identity"

    def test_is_service_principal_property(self):
        """Test is_service_principal property."""
        assert AuthMethod.SERVICE_PRINCIPAL_SECRET.is_service_principal is True
        assert AuthMethod.SERVICE_PRINCIPAL_CERTIFICATE.is_service_principal is True
        assert AuthMethod.AZURE_CLI.is_service_principal is False
        assert AuthMethod.MANAGED_IDENTITY.is_service_principal is False

    def test_requires_config_property(self):
        """Test requires_config property."""
        assert AuthMethod.SERVICE_PRINCIPAL_SECRET.requires_config is True
        assert AuthMethod.SERVICE_PRINCIPAL_CERTIFICATE.requires_config is True
        assert AuthMethod.MANAGED_IDENTITY.requires_config is True
        assert AuthMethod.AZURE_CLI.requires_config is False


class TestServicePrincipalConfig:
    """Test ServicePrincipalConfig dataclass."""

    def test_valid_config(self):
        """Test creating valid service principal config."""
        config = ServicePrincipalConfig(
            tenant_id="12345678-1234-1234-1234-123456789012",
            client_id="87654321-4321-4321-4321-210987654321",
        )
        assert config.tenant_id == "12345678-1234-1234-1234-123456789012"
        assert config.client_id == "87654321-4321-4321-4321-210987654321"
        assert config.use_certificate is False
        assert config.certificate_path is None

    def test_invalid_tenant_id(self):
        """Test that invalid tenant_id is rejected."""
        with pytest.raises(ValueError, match="tenant_id"):
            ServicePrincipalConfig(
                tenant_id="not-a-uuid",
                client_id="87654321-4321-4321-4321-210987654321",
            )

    def test_invalid_client_id(self):
        """Test that invalid client_id is rejected."""
        with pytest.raises(ValueError, match="client_id"):
            ServicePrincipalConfig(
                tenant_id="12345678-1234-1234-1234-123456789012",
                client_id="invalid-id",
            )

    def test_to_dict(self):
        """Test to_dict serialization."""
        config = ServicePrincipalConfig(
            tenant_id="12345678-1234-1234-1234-123456789012",
            client_id="87654321-4321-4321-4321-210987654321",
        )
        config_dict = config.to_dict()
        assert "tenant_id" in config_dict
        assert "client_id" in config_dict
        assert config_dict["tenant_id"] == "12345678-1234-1234-1234-123456789012"

    def test_to_dict_masked(self):
        """Test to_dict_masked masks certificate path."""
        config = ServicePrincipalConfig(
            tenant_id="12345678-1234-1234-1234-123456789012",
            client_id="87654321-4321-4321-4321-210987654321",
            certificate_path="/home/user/.azlin/super-secret.pem",
            use_certificate=True,
        )
        masked = config.to_dict_masked()
        assert "****" in masked["certificate_path"]
        assert "super-secret.pem" in masked["certificate_path"]

    def test_frozen_immutability(self):
        """Test that config is immutable (frozen)."""
        config = ServicePrincipalConfig(
            tenant_id="12345678-1234-1234-1234-123456789012",
            client_id="87654321-4321-4321-4321-210987654321",
        )
        with pytest.raises(Exception):
            config.tenant_id = "new-value"


class TestManagedIdentityConfig:
    """Test ManagedIdentityConfig dataclass."""

    def test_config_without_client_id(self):
        """Test MI config without client_id (system-assigned)."""
        config = ManagedIdentityConfig()
        assert config.client_id is None

    def test_config_with_client_id(self):
        """Test MI config with client_id (user-assigned)."""
        config = ManagedIdentityConfig(
            client_id="12345678-1234-1234-1234-123456789012"
        )
        assert config.client_id == "12345678-1234-1234-1234-123456789012"

    def test_invalid_client_id(self):
        """Test that invalid client_id is rejected."""
        with pytest.raises(ValueError, match="client_id"):
            ManagedIdentityConfig(client_id="invalid-uuid")


class TestAuthConfig:
    """Test AuthConfig dataclass."""

    def test_service_principal_secret_config(self):
        """Test SP with client secret config."""
        sp_config = ServicePrincipalConfig(
            tenant_id="12345678-1234-1234-1234-123456789012",
            client_id="87654321-4321-4321-4321-210987654321",
        )
        auth_config = AuthConfig(
            method=AuthMethod.SERVICE_PRINCIPAL_SECRET,
            service_principal=sp_config,
        )
        assert auth_config.method == AuthMethod.SERVICE_PRINCIPAL_SECRET
        assert auth_config.service_principal == sp_config

    def test_sp_method_requires_sp_config(self):
        """Test that SP method requires SP config."""
        with pytest.raises(ValueError, match="service_principal"):
            AuthConfig(method=AuthMethod.SERVICE_PRINCIPAL_SECRET)

    def test_cert_method_requires_certificate(self):
        """Test that cert method requires certificate."""
        sp_config = ServicePrincipalConfig(
            tenant_id="12345678-1234-1234-1234-123456789012",
            client_id="87654321-4321-4321-4321-210987654321",
            use_certificate=False,
        )
        with pytest.raises(ValueError, match="certificate"):
            AuthConfig(
                method=AuthMethod.SERVICE_PRINCIPAL_CERTIFICATE,
                service_principal=sp_config,
            )

    def test_managed_identity_requires_mi_config(self):
        """Test that MI method requires MI config."""
        with pytest.raises(ValueError, match="managed_identity"):
            AuthConfig(method=AuthMethod.MANAGED_IDENTITY)

    def test_azure_cli_no_config_allowed(self):
        """Test that Azure CLI should not have configs."""
        sp_config = ServicePrincipalConfig(
            tenant_id="12345678-1234-1234-1234-123456789012",
            client_id="87654321-4321-4321-4321-210987654321",
        )
        with pytest.raises(ValueError):
            AuthConfig(
                method=AuthMethod.AZURE_CLI,
                service_principal=sp_config,
            )


class TestAuthContext:
    """Test AuthContext dataclass."""

    def test_basic_context(self):
        """Test creating basic auth context."""
        ctx = AuthContext(method=AuthMethod.AZURE_CLI)
        assert ctx.method == AuthMethod.AZURE_CLI
        assert ctx.subscription_id is None

    def test_context_with_subscription(self):
        """Test context with subscription_id."""
        ctx = AuthContext(
            method=AuthMethod.AZURE_CLI,
            subscription_id="12345678-1234-1234-1234-123456789012",
        )
        assert ctx.subscription_id == "12345678-1234-1234-1234-123456789012"

    def test_mutability(self):
        """Test that AuthContext is mutable."""
        ctx = AuthContext(method=AuthMethod.AZURE_CLI)
        ctx.resource_group = "new-rg"
        assert ctx.resource_group == "new-rg"

    def test_invalid_subscription_id(self):
        """Test that invalid subscription_id is rejected."""
        with pytest.raises(ValueError, match="subscription_id"):
            AuthContext(
                method=AuthMethod.AZURE_CLI,
                subscription_id="invalid-uuid",
            )


class TestChainResult:
    """Test ChainResult dataclass."""

    def test_success_result(self):
        """Test successful chain result."""
        result = ChainResult(
            success=True,
            method=AuthMethod.AZURE_CLI,
            credentials=None,
        )
        assert result.success is True
        assert result.method == AuthMethod.AZURE_CLI
        assert result.error is None

    def test_failure_result(self):
        """Test failed chain result."""
        result = ChainResult(
            success=False,
            error="Authentication failed",
        )
        assert result.success is False
        assert result.method is None
        assert result.error == "Authentication failed"


class TestCertificateInfo:
    """Test CertificateInfo dataclass."""

    def test_valid_certificate(self):
        """Test certificate info with valid file."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".pem", delete=False) as f:
            f.write("-----BEGIN CERTIFICATE-----\nfake\n-----END CERTIFICATE-----")
            cert_path = f.name

        try:
            cert_info = CertificateInfo(
                path=cert_path,
                thumbprint="ABC123",
                is_valid=True,
            )
            assert cert_info.path == cert_path
            assert cert_info.is_valid is True
            assert len(cert_info.validation_errors) == 0
        finally:
            os.unlink(cert_path)

    def test_missing_certificate(self):
        """Test certificate info with missing file."""
        cert_info = CertificateInfo(
            path="/tmp/nonexistent.pem",
            is_valid=True,
        )
        assert cert_info.is_valid is False
        assert len(cert_info.validation_errors) > 0


class TestCertificateValidation:
    """Test CertificateValidation dataclass."""

    def test_valid_certificate_validation(self):
        """Test valid certificate validation result."""
        validation = CertificateValidation(
            is_valid=True,
            path="/path/to/cert.pem",
            permissions_ok=True,
            exists=True,
            expiration_status="valid",
        )
        assert validation.is_valid is True
        assert validation.permissions_ok is True

    def test_invalid_certificate_validation(self):
        """Test invalid certificate validation result."""
        validation = CertificateValidation(
            is_valid=False,
            path="/path/to/cert.pem",
            permissions_ok=False,
            exists=True,
            expiration_status="expired",
            errors=["Certificate has expired"],
        )
        assert validation.is_valid is False
        assert len(validation.errors) > 0
