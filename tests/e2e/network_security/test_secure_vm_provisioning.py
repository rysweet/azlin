"""End-to-end tests for secure VM provisioning workflow.

Tests complete workflows from VM creation through secure access with all security features.
These tests follow TDD RED phase - they will fail until implementation is complete.

Coverage targets:
- Complete secure VM provisioning workflow
- NSG template → Bastion → Audit logging integration
- Security scanning before deployment
- Compliance report generation
- VPN + private endpoint secure infrastructure
"""

import pytest
from unittest.mock import Mock, patch
from datetime import datetime

# Mark all tests as E2E and TDD RED phase
pytestmark = [pytest.mark.e2e, pytest.mark.tdd_red]


class TestSecureVMProvisioningWorkflow:
    """Test end-to-end secure VM provisioning with all security features."""

    @patch("subprocess.run")
    def test_complete_secure_vm_provisioning_workflow(self, mock_run, tmp_path):
        """Complete workflow: NSG validation → VM creation → Bastion tunnel → Audit."""
        from azlin.network_security.nsg_manager import NSGManager
        from azlin.network_security.nsg_validator import NSGValidator
        from azlin.network_security.bastion_connection_pool import (
            BastionConnectionPool,
        )
        from azlin.network_security.security_audit import (
            SecurityAuditLogger,
            AuditEventType,
        )
        from azlin.bastion_manager import BastionManager

        mock_run.return_value = Mock(returncode=0, stdout="{}")

        # Step 1: Create NSG template
        template_path = tmp_path / "secure-vm-nsg.yaml"
        template_path.write_text(
            """
name: secure-vm-nsg
description: Locked down VM - Bastion only
version: 1.0
metadata:
  compliance:
    - CIS-6.1
    - CIS-6.2
    - SOC2-CC6.6
security_rules:
  - name: deny-ssh-internet
    priority: 200
    direction: Inbound
    access: Deny
    protocol: Tcp
    source_port_range: "*"
    destination_port_range: "22"
    source_address_prefix: "Internet"
    destination_address_prefix: "*"
    justification: Block SSH from internet
  - name: deny-all-inbound
    priority: 4096
    direction: Inbound
    access: Deny
    protocol: "*"
    source_port_range: "*"
    destination_port_range: "*"
    source_address_prefix: "*"
    destination_address_prefix: "*"
    justification: Default deny
default_rules:
  outbound: Allow
  inbound: Deny
"""
        )

        # Step 2: Validate and apply NSG
        validator = NSGValidator()
        logger = SecurityAuditLogger()
        nsg_manager = NSGManager(validator, logger)

        result = nsg_manager.apply_template(
            template_path=str(template_path),
            nsg_name="secure-vm-nsg",
            resource_group="test-rg",
            dry_run=False,
        )

        # Verify NSG application succeeded
        assert result.success is True

        # Step 3: Create VM (mocked)
        # In real workflow, VM would be created here

        # Step 4: Create Bastion tunnel using connection pool
        bastion_manager = BastionManager()
        pool = BastionConnectionPool(bastion_manager)

        with patch.object(bastion_manager, "create_tunnel") as mock_create:
            with patch.object(bastion_manager, "check_tunnel_health", return_value=True):
                mock_tunnel = Mock()
                mock_tunnel.local_port = 50000
                mock_create.return_value = mock_tunnel

                pooled_tunnel = pool.get_or_create_tunnel(
                    bastion_name="test-bastion",
                    resource_group="test-rg",
                    target_vm_id="/subscriptions/test/vm1",
                    remote_port=22,
                )

        # Verify tunnel created
        assert pooled_tunnel.tunnel is not None

        # Step 5: Verify audit trail
        events = logger.query_events()
        assert len(events) > 0

        # Verify NSG application was logged
        nsg_events = [e for e in events if e.event_type == AuditEventType.NSG_RULE_APPLY]
        assert len(nsg_events) > 0
        assert nsg_events[0].outcome == "success"

        # Verify compliance tags present
        assert "CIS-6.1" in nsg_events[0].compliance_tags

    @patch("subprocess.run")
    def test_security_scan_blocks_insecure_deployment(self, mock_run, tmp_path):
        """Security scan should block deployment with critical findings."""
        from azlin.network_security.security_scanner import SecurityScanner
        from azlin.network_security.nsg_validator import NSGValidator

        # Create insecure NSG template
        template = {
            "resources": [
                {
                    "type": "Microsoft.Network/networkSecurityGroups",
                    "name": "insecure-nsg",
                    "properties": {
                        "securityRules": [
                            {
                                "name": "allow-ssh-internet",
                                "priority": 100,
                                "direction": "Inbound",
                                "access": "Allow",
                                "protocol": "Tcp",
                                "destinationPortRange": "22",
                                "sourceAddressPrefix": "*",
                            }
                        ]
                    },
                }
            ]
        }

        scanner = SecurityScanner(subscription_id="test-sub")

        with patch(
            "azlin.network_security.nsg_validator.NSGValidator"
        ) as mock_validator_class:
            mock_validator = Mock(spec=NSGValidator)
            mock_validator.validate_template.return_value = Mock(
                critical_issues=[
                    {
                        "title": "SSH exposed to internet",
                        "description": "Port 22 is open to 0.0.0.0/0",
                        "remediation": "Use Bastion instead",
                        "compliance_impact": ["CIS-6.2"],
                    }
                ]
            )
            mock_validator_class.return_value = mock_validator

            # Run pre-deployment scan
            can_deploy, findings = scanner.pre_deployment_scan(
                resource_group="test-rg", template=template
            )

        # Verify deployment is blocked
        assert can_deploy is False
        assert len(findings) > 0
        assert any("ssh" in f.title.lower() for f in findings)


class TestComplianceReportingWorkflow:
    """Test end-to-end compliance reporting workflow."""

    def test_generate_compliance_report_for_period(self):
        """Generate compliance report for specific time period."""
        from azlin.network_security.security_audit import (
            SecurityAuditLogger,
            AuditEvent,
            AuditEventType,
        )

        logger = SecurityAuditLogger()

        # Simulate security operations over time
        operations = [
            {
                "event_type": AuditEventType.NSG_RULE_APPLY,
                "resource": "web-nsg",
                "compliance_tags": ["CIS-6.2", "SOC2-CC6.6"],
                "severity": "info",
            },
            {
                "event_type": AuditEventType.BASTION_TUNNEL_CREATE,
                "resource": "prod-bastion",
                "compliance_tags": ["CIS-6.5", "SOC2-CC6.6"],
                "severity": "info",
            },
            {
                "event_type": AuditEventType.NSG_VALIDATION_FAIL,
                "resource": "bad-nsg",
                "compliance_tags": ["CIS-6.1"],
                "severity": "critical",
            },
        ]

        for op in operations:
            event = AuditEvent(
                event_id=f"event-{operations.index(op)}",
                timestamp=datetime.now(),
                event_type=op["event_type"],
                user="test-user",
                resource=op["resource"],
                action="test",
                outcome="test",
                details={},
                severity=op["severity"],
                compliance_tags=op["compliance_tags"],
            )
            logger.log_event(event)

        # Generate CIS compliance report
        cis_report = logger.generate_compliance_report(
            framework="CIS",
            start_date=datetime.now(),
            end_date=datetime.now(),
        )

        # Verify report structure
        assert "framework" in cis_report
        assert "total_events" in cis_report
        assert "critical_findings" in cis_report

        # Verify critical finding counted
        assert cis_report["critical_findings"] == 1

        # Generate SOC2 compliance report
        soc2_report = logger.generate_compliance_report(
            framework="SOC2",
            start_date=datetime.now(),
            end_date=datetime.now(),
        )

        # Verify SOC2 events captured
        assert soc2_report["total_events"] >= 2  # NSG + Bastion


class TestSecureInfrastructureSetup:
    """Test end-to-end secure infrastructure setup with VPN and private endpoints."""

    @patch("subprocess.run")
    def test_complete_secure_infrastructure_workflow(self, mock_run):
        """Complete workflow: VPN + Private Endpoints + Private DNS + Audit."""
        from azlin.network_security.vpn_manager import VPNManager
        from azlin.network_security.private_endpoint_manager import (
            PrivateEndpointManager,
        )
        from azlin.network_security.security_audit import (
            SecurityAuditLogger,
            AuditEvent,
            AuditEventType,
        )

        mock_run.return_value = Mock(returncode=0, stdout="{}")

        logger = SecurityAuditLogger()

        # Step 1: Create VPN gateway for remote access
        vpn_manager = VPNManager(resource_group="secure-rg")

        with patch.object(vpn_manager, "_get_gateway_id", return_value="/gateway/id"):
            vpn_id = vpn_manager.create_point_to_site_vpn(
                vnet_name="secure-vnet",
                vpn_gateway_name="secure-vpn-gw",
                address_pool="172.16.0.0/24",
            )

        assert vpn_id is not None

        # Log VPN creation
        logger.log_event(
            AuditEvent(
                event_id="vpn-1",
                timestamp=datetime.now(),
                event_type="vpn_gateway_create",
                user="admin",
                resource="secure-vpn-gw",
                action="create_p2s_vpn",
                outcome="success",
                details={"address_pool": "172.16.0.0/24"},
                severity="info",
                compliance_tags=["CIS-6.3", "SOC2-CC6.6"],
            )
        )

        # Step 2: Create private endpoint for Key Vault
        pe_manager = PrivateEndpointManager()

        with patch.object(pe_manager, "_get_endpoint_id", return_value="/endpoint/id"):
            pe_id = pe_manager.create_private_endpoint(
                endpoint_name="kv-pe",
                resource_group="secure-rg",
                vnet_name="secure-vnet",
                subnet_name="pe-subnet",
                service_resource_id="/subscriptions/test/keyvault1",
                group_id="vault",
            )

        assert pe_id is not None

        # Step 3: Create Private DNS zone
        pe_manager.create_private_dns_zone(
            zone_name="privatelink.vaultcore.azure.net",
            resource_group="secure-rg",
            vnet_name="secure-vnet",
        )

        # Log private endpoint creation
        logger.log_event(
            AuditEvent(
                event_id="pe-1",
                timestamp=datetime.now(),
                event_type="private_endpoint_create",
                user="admin",
                resource="kv-pe",
                action="create_private_endpoint",
                outcome="success",
                details={"service": "KeyVault", "dns_zone": "privatelink.vaultcore.azure.net"},
                severity="info",
                compliance_tags=["CIS-6.3", "SOC2-CC6.6"],
            )
        )

        # Step 4: Verify audit trail
        events = logger.query_events()
        assert len(events) >= 2  # VPN + Private Endpoint

        # Step 5: Generate compliance report
        report = logger.generate_compliance_report(
            framework="SOC2",
            start_date=datetime.now(),
            end_date=datetime.now(),
        )

        assert report["total_events"] >= 2


class TestAuditLogIntegrity:
    """Test end-to-end audit log integrity verification."""

    def test_audit_log_integrity_workflow(self):
        """Complete workflow: Log events → Verify integrity → Detect tampering."""
        from azlin.network_security.security_audit import (
            SecurityAuditLogger,
            AuditEvent,
            AuditEventType,
        )

        logger = SecurityAuditLogger()

        # Log multiple security events
        for i in range(5):
            event = AuditEvent(
                event_id=f"event-{i}",
                timestamp=datetime.now(),
                event_type=AuditEventType.NSG_RULE_APPLY,
                user="test-user",
                resource=f"nsg-{i}",
                action="apply_template",
                outcome="success",
                details={},
                severity="info",
                compliance_tags=["CIS-6.2"],
            )
            logger.log_event(event)

        # Verify integrity
        is_valid, corrupted = logger.verify_integrity()

        # All events should be valid (no tampering)
        assert is_valid is True
        assert len(corrupted) == 0

    def test_detect_tampered_audit_log(self, tmp_path):
        """Integrity verification should detect tampered events."""
        from azlin.network_security.security_audit import (
            SecurityAuditLogger,
            AuditEvent,
            AuditEventType,
        )
        import json

        logger = SecurityAuditLogger()

        # Log legitimate event
        event = AuditEvent(
            event_id="event-1",
            timestamp=datetime.now(),
            event_type=AuditEventType.NSG_RULE_APPLY,
            user="alice",
            resource="nsg-1",
            action="apply_template",
            outcome="success",
            details={},
            severity="info",
            compliance_tags=[],
        )
        logger.log_event(event)

        # Manually tamper with audit log (change user)
        with open(logger.AUDIT_FILE, "r") as f:
            lines = f.readlines()

        # Modify first line (change user)
        event_dict = json.loads(lines[0])
        event_dict["user"] = "bob"  # Tampering!

        with open(logger.AUDIT_FILE, "w") as f:
            f.write(json.dumps(event_dict) + "\n")

        # Verify integrity - should detect tampering
        is_valid, corrupted = logger.verify_integrity()

        assert is_valid is False
        assert len(corrupted) > 0
