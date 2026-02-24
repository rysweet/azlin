"""Unit tests for service_principal_auth module.

Tests ServicePrincipalConfig and ServicePrincipalManager with mocked filesystem
and environment:
- Config dataclass (to_dict, from_dict, repr masking)
- UUID validation
- Config validation (auth methods, cert path security)
- Config loading from TOML (permissions, path security, missing fields)
- Config saving (atomic write, secret exclusion)
- Credential retrieval (client_secret and certificate modes)
- Certificate validation delegation
- Credential context manager
- clear_credentials
"""

import os
import stat
import warnings
from pathlib import Path
from unittest.mock import patch

import pytest

from azlin.service_principal_auth import (
    ServicePrincipalConfig,
    ServicePrincipalError,
    ServicePrincipalManager,
)

# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

VALID_UUID = "12345678-1234-1234-1234-123456789abc"
VALID_UUID_2 = "abcdef01-2345-6789-abcd-ef0123456789"
VALID_UUID_3 = "00000000-0000-0000-0000-000000000001"


def _make_config(**overrides):
    """Create a ServicePrincipalConfig with valid defaults."""
    defaults = {
        "client_id": VALID_UUID,
        "tenant_id": VALID_UUID_2,
        "subscription_id": VALID_UUID_3,
        "auth_method": "client_secret",
    }
    defaults.update(overrides)
    return ServicePrincipalConfig(**defaults)


# ===========================================================================
# ServicePrincipalConfig dataclass
# ===========================================================================


class TestServicePrincipalConfig:
    """Tests for the config dataclass."""

    def test_to_dict_excludes_secret_by_default(self):
        config = _make_config(client_secret="supersecret")  # noqa: S106
        d = config.to_dict()
        assert "client_secret" not in d
        assert d["client_id"] == VALID_UUID

    def test_to_dict_includes_secret_when_requested(self):
        config = _make_config(client_secret="supersecret")  # noqa: S106
        d = config.to_dict(include_secret=True)
        assert d["client_secret"] == "supersecret"  # noqa: S105

    def test_to_dict_includes_certificate_path(self):
        config = _make_config(auth_method="certificate", certificate_path=Path("/tmp/cert.pem"))
        d = config.to_dict()
        assert d["certificate_path"] == "/tmp/cert.pem"

    def test_from_dict_round_trip(self):
        original = _make_config(auth_method="certificate", certificate_path=Path("/tmp/cert.pem"))
        d = original.to_dict()
        d["auth_method"] = "certificate"
        restored = ServicePrincipalConfig.from_dict(d)
        assert restored.client_id == original.client_id
        assert restored.certificate_path == original.certificate_path

    def test_repr_masks_secret(self):
        config = _make_config(client_secret="supersecret")  # noqa: S106
        r = repr(config)
        assert "supersecret" not in r
        assert "****" in r

    def test_repr_no_secret(self):
        config = _make_config()
        r = repr(config)
        assert "None" in r


# ===========================================================================
# UUID validation
# ===========================================================================


class TestUUIDValidation:
    """Tests for validate_uuid."""

    def test_valid_uuid(self):
        assert ServicePrincipalManager.validate_uuid(VALID_UUID) is True

    def test_upper_case_uuid(self):
        assert ServicePrincipalManager.validate_uuid(VALID_UUID.upper()) is True

    def test_invalid_uuid_too_short(self):
        assert ServicePrincipalManager.validate_uuid("1234-5678") is False

    def test_invalid_uuid_empty(self):
        assert ServicePrincipalManager.validate_uuid("") is False

    def test_invalid_uuid_none_like(self):
        assert ServicePrincipalManager.validate_uuid(None) is False  # type: ignore[arg-type]

    def test_invalid_uuid_bad_chars(self):
        assert (
            ServicePrincipalManager.validate_uuid("zzzzzzzz-zzzz-zzzz-zzzz-zzzzzzzzzzzz") is False
        )


# ===========================================================================
# Config validation
# ===========================================================================


class TestValidateConfig:
    """Tests for validate_config."""

    def test_valid_config_client_secret(self):
        config = _make_config()
        # Should not raise
        ServicePrincipalManager.validate_config(config)

    def test_valid_config_certificate(self):
        config = _make_config(auth_method="certificate", certificate_path=Path("/tmp/cert.pem"))
        ServicePrincipalManager.validate_config(config)

    def test_invalid_client_id(self):
        config = _make_config(client_id="not-a-uuid")
        with pytest.raises(ServicePrincipalError, match="Invalid UUID.*client_id"):
            ServicePrincipalManager.validate_config(config)

    def test_invalid_tenant_id(self):
        config = _make_config(tenant_id="bad")
        with pytest.raises(ServicePrincipalError, match="Invalid UUID.*tenant_id"):
            ServicePrincipalManager.validate_config(config)

    def test_invalid_subscription_id(self):
        config = _make_config(subscription_id="bad")
        with pytest.raises(ServicePrincipalError, match="Invalid UUID.*subscription_id"):
            ServicePrincipalManager.validate_config(config)

    def test_invalid_auth_method(self):
        config = _make_config(auth_method="oauth")
        with pytest.raises(ServicePrincipalError, match="Invalid auth_method"):
            ServicePrincipalManager.validate_config(config)

    def test_certificate_method_requires_path(self):
        config = _make_config(auth_method="certificate", certificate_path=None)
        with pytest.raises(ServicePrincipalError, match="requires certificate_path"):
            ServicePrincipalManager.validate_config(config)

    def test_certificate_path_traversal_rejected(self):
        config = _make_config(auth_method="certificate", certificate_path=Path("../../etc/passwd"))
        with pytest.raises(ServicePrincipalError, match="Invalid certificate path"):
            ServicePrincipalManager.validate_config(config)

    def test_certificate_path_shell_metachar_rejected(self):
        config = _make_config(
            auth_method="certificate",
            certificate_path=Path("/tmp/cert;rm -rf /"),
        )
        with pytest.raises(ServicePrincipalError, match="Invalid certificate path"):
            ServicePrincipalManager.validate_config(config)


# ===========================================================================
# get_credentials
# ===========================================================================


class TestGetCredentials:
    """Tests for get_credentials."""

    def test_client_secret_mode(self, monkeypatch):
        monkeypatch.setenv("AZLIN_SP_CLIENT_SECRET", "test-secret")
        config = _make_config()
        creds = ServicePrincipalManager.get_credentials(config)
        assert creds["AZURE_CLIENT_ID"] == VALID_UUID
        assert creds["AZURE_CLIENT_SECRET"] == "test-secret"  # noqa: S105

    def test_client_secret_missing(self, monkeypatch):
        monkeypatch.delenv("AZLIN_SP_CLIENT_SECRET", raising=False)
        monkeypatch.delenv("AZURE_CLIENT_SECRET", raising=False)
        config = _make_config()
        with pytest.raises(ServicePrincipalError, match="AZLIN_SP_CLIENT_SECRET"):
            ServicePrincipalManager.get_credentials(config)

    @patch.object(ServicePrincipalManager, "validate_certificate", return_value=True)
    def test_certificate_mode(self, mock_validate, tmp_path):
        cert_path = tmp_path / "cert.pem"
        cert_path.touch()
        config = _make_config(auth_method="certificate", certificate_path=cert_path)
        creds = ServicePrincipalManager.get_credentials(config)
        assert creds["AZURE_CLIENT_CERTIFICATE_PATH"] == str(cert_path)
        mock_validate.assert_called_once()

    def test_certificate_mode_no_path(self):
        config = _make_config(auth_method="certificate", certificate_path=None)
        with pytest.raises(ServicePrincipalError, match="Certificate path required"):
            ServicePrincipalManager.get_credentials(config)

    def test_unsupported_auth_method(self):
        config = _make_config(auth_method="magic")
        with pytest.raises(ServicePrincipalError, match="Unsupported auth method"):
            ServicePrincipalManager.get_credentials(config)


# ===========================================================================
# load_config
# ===========================================================================


class TestLoadConfig:
    """Tests for load_config with temp files."""

    def _write_toml(self, path, content):
        """Write TOML content to path with secure permissions."""
        path.write_text(content)
        path.chmod(0o600)

    def test_load_valid_config(self, tmp_path):
        cfg = tmp_path / "sp-config.toml"
        self._write_toml(
            cfg,
            f"""
[service_principal]
client_id = "{VALID_UUID}"
tenant_id = "{VALID_UUID_2}"
subscription_id = "{VALID_UUID_3}"
auth_method = "client_secret"
""",
        )
        config = ServicePrincipalManager.load_config(str(cfg))
        assert config.client_id == VALID_UUID
        assert config.auth_method == "client_secret"

    def test_load_config_file_not_found(self, tmp_path):
        with pytest.raises(ServicePrincipalError, match="Config file not found"):
            ServicePrincipalManager.load_config(str(tmp_path / "missing.toml"))

    def test_load_config_missing_section(self, tmp_path):
        cfg = tmp_path / "sp-config.toml"
        self._write_toml(cfg, '[other]\nkey = "val"\n')
        with pytest.raises(ServicePrincipalError, match="Missing.*service_principal"):
            ServicePrincipalManager.load_config(str(cfg))

    def test_load_config_missing_required_field(self, tmp_path):
        cfg = tmp_path / "sp-config.toml"
        self._write_toml(
            cfg,
            f"""
[service_principal]
client_id = "{VALID_UUID}"
tenant_id = "{VALID_UUID_2}"
auth_method = "client_secret"
""",
        )
        with pytest.raises(ServicePrincipalError, match="Missing required field"):
            ServicePrincipalManager.load_config(str(cfg))

    def test_load_config_rejects_inline_secret(self, tmp_path):
        cfg = tmp_path / "sp-config.toml"
        self._write_toml(
            cfg,
            f"""
[service_principal]
client_id = "{VALID_UUID}"
tenant_id = "{VALID_UUID_2}"
subscription_id = "{VALID_UUID_3}"
auth_method = "client_secret"
client_secret = "should-not-be-here"
""",
        )
        with pytest.raises(ServicePrincipalError, match="client_secret not allowed"):
            ServicePrincipalManager.load_config(str(cfg))

    def test_load_config_path_traversal_rejected(self):
        with pytest.raises(ServicePrincipalError, match="Invalid config path"):
            ServicePrincipalManager.load_config("../../etc/shadow")

    def test_load_config_shell_metachar_rejected(self):
        with pytest.raises(ServicePrincipalError, match="Invalid config path"):
            ServicePrincipalManager.load_config("/tmp/config;rm -rf /")

    def test_load_config_sensitive_dir_rejected(self):
        with pytest.raises(ServicePrincipalError, match="Invalid config path"):
            ServicePrincipalManager.load_config("/etc/passwd")

    def test_load_config_fixes_insecure_permissions(self, tmp_path):
        cfg = tmp_path / "sp-config.toml"
        cfg.write_text(
            f"""
[service_principal]
client_id = "{VALID_UUID}"
tenant_id = "{VALID_UUID_2}"
subscription_id = "{VALID_UUID_3}"
auth_method = "client_secret"
"""
        )
        cfg.chmod(0o644)  # Insecure
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            config = ServicePrincipalManager.load_config(str(cfg))
            assert any("insecure permissions" in str(warning.message) for warning in w)
        # File permissions should have been fixed
        mode = stat.S_IMODE(cfg.stat().st_mode)
        assert mode == 0o600


# ===========================================================================
# save_config
# ===========================================================================


class TestSaveConfig:
    """Tests for save_config."""

    def test_save_and_reload(self, tmp_path):
        pytest.importorskip("tomli_w")
        cfg_path = tmp_path / "sp-config.toml"
        config = _make_config(client_secret="should-not-persist")  # noqa: S106
        ServicePrincipalManager.save_config(config, str(cfg_path))

        assert cfg_path.exists()
        content = cfg_path.read_text()
        assert "should-not-persist" not in content
        assert VALID_UUID in content

        # Verify permissions
        mode = stat.S_IMODE(cfg_path.stat().st_mode)
        assert mode == 0o600

    def test_save_config_no_tomli_w(self, tmp_path, monkeypatch):
        monkeypatch.setattr("azlin.service_principal_auth.tomli_w", None)
        config = _make_config()
        with pytest.raises(ServicePrincipalError, match="tomli_w"):
            ServicePrincipalManager.save_config(config, str(tmp_path / "out.toml"))


# ===========================================================================
# validate_certificate (integration with CertificateValidator)
# ===========================================================================


class TestValidateCertificate:
    """Tests for validate_certificate."""

    def test_certificate_not_found(self, tmp_path):
        with pytest.raises(ServicePrincipalError, match="not found"):
            ServicePrincipalManager.validate_certificate(tmp_path / "missing.pem")

    def test_invalid_format_no_pem_headers(self, tmp_path):
        cert = tmp_path / "bad.pem"
        cert.write_text("not a certificate")
        cert.chmod(0o600)
        with pytest.raises(ServicePrincipalError, match="Invalid certificate format"):
            ServicePrincipalManager.validate_certificate(cert)

    def test_valid_short_pem_passes(self, tmp_path):
        """A short PEM with correct headers but fake data is accepted (test data).

        The code treats certs with <= 3 lines as test data and skips parse_certificate.
        """
        cert = tmp_path / "test.pem"
        # Exactly 3 lines (split produces 3 elements) so parse_certificate is skipped
        cert.write_text("-----BEGIN CERTIFICATE-----\nFAKEDATA\n-----END CERTIFICATE-----")
        cert.chmod(0o600)
        # Mock out the expiration check since fake cert won't parse
        with patch.object(
            ServicePrincipalManager, "_get_certificate_expiration", return_value=None
        ):
            result = ServicePrincipalManager.validate_certificate(cert)
            assert result is True

    @patch("azlin.service_principal_auth.CertificateValidator.check_permissions")
    def test_insecure_permissions_rejected(self, mock_check, tmp_path):
        cert = tmp_path / "cert.pem"
        cert.write_text("-----BEGIN CERTIFICATE-----\nFAKE\n-----END CERTIFICATE-----\n")
        cert.chmod(0o644)
        mock_check.return_value = (
            False,
            [],
            ["Certificate has insecure permissions 0o644"],
        )
        with pytest.raises(ServicePrincipalError, match="insecure permissions"):
            ServicePrincipalManager.validate_certificate(cert)


# ===========================================================================
# clear_credentials
# ===========================================================================


class TestClearCredentials:
    """Tests for clear_credentials."""

    def test_clears_all_azure_env_vars(self, monkeypatch):
        env_vars = [
            "AZURE_CLIENT_ID",
            "AZURE_CLIENT_SECRET",
            "AZURE_TENANT_ID",
            "AZURE_SUBSCRIPTION_ID",
            "AZURE_CLIENT_CERTIFICATE_PATH",
            "AZLIN_SP_CLIENT_SECRET",
        ]
        for var in env_vars:
            monkeypatch.setenv(var, "test-value")

        ServicePrincipalManager.clear_credentials()

        for var in env_vars:
            assert var not in os.environ

    def test_clear_noop_when_not_set(self):
        # Should not raise even if vars aren't set
        ServicePrincipalManager.clear_credentials()


# ===========================================================================
# _validate_env_var_name
# ===========================================================================


class TestValidateEnvVarName:
    """Tests for _validate_env_var_name."""

    def test_valid_names(self):
        assert ServicePrincipalManager._validate_env_var_name("AZURE_CLIENT_ID") is True
        assert ServicePrincipalManager._validate_env_var_name("MY_VAR") is True

    def test_invalid_names(self):
        assert ServicePrincipalManager._validate_env_var_name("") is False
        assert ServicePrincipalManager._validate_env_var_name(None) is False  # type: ignore[arg-type]
        assert ServicePrincipalManager._validate_env_var_name("VAR;rm") is False
        assert ServicePrincipalManager._validate_env_var_name("VAR|pipe") is False
        assert ServicePrincipalManager._validate_env_var_name("$VAR") is False
