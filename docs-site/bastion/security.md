# Azure Bastion Security Benefits

Azure Bastion provides secure SSH access to VMs without exposing them to the public internet.

## Key Security Benefits

### No Public IP Required

VMs connected through Bastion don't need public IP addresses, eliminating a major attack surface:

- No port scanning exposure
- No brute force SSH attempts from the internet
- Reduced network attack surface

### Azure AD Authentication

Bastion integrates with Azure Active Directory for centralized identity management:

- Multi-factor authentication (MFA)
- Conditional access policies
- Audit logging of all access

### TLS-Encrypted Tunnels

All traffic between the client and Bastion is encrypted with TLS 1.2+:

- End-to-end encryption
- Certificate-based authentication
- No VPN required

### NSG Simplification

With Bastion, Network Security Groups can be significantly simplified:

- No inbound SSH (port 22) rules needed on VMs
- Only Bastion subnet needs inbound HTTPS (443)
- Reduced misconfiguration risk

## How azlin Uses Bastion

azlin automatically detects and uses Bastion when available:

```bash
# Connect through Bastion (automatic if VM has no public IP)
azlin connect myvm

# Explicit Bastion usage
azlin bastion status

# GUI features work through Bastion too
azlin connect --x11 myvm     # X11 forwarding through Bastion
azlin gui myvm                # VNC through Bastion tunnel
```

All azlin features, including file transfer, session management, and GUI forwarding, work transparently through Bastion tunnels.

## Cost Considerations

Azure Bastion has an hourly cost. See [Cost Analysis](cost.md) for pricing details and optimization strategies.

## See Also

- [Bastion Setup](setup.md)
- [Connecting via Bastion](connecting.md)
- [Cost Analysis](cost.md)
