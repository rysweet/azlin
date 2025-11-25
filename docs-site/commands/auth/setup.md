# azlin auth setup

**Configure service principal authentication for automated workflows**

## Description

The `azlin auth setup` command creates authentication profiles for Azure service principal authentication, enabling azlin to run in automated environments like CI/CD pipelines, GitHub Actions, or cron jobs. It supports both certificate-based and client secret authentication methods.

**Use cases:**
- CI/CD pipeline automation (GitHub Actions, GitLab CI, Jenkins)
- Scheduled VM management (cron jobs, Azure Automation)
- Multi-tenant Azure environments
- Secure automated deployments
- Rotating service principal credentials

**Why service principals?**
- **Non-interactive**: No manual login required
- **Secure**: Certificate or secret-based authentication
- **Scoped**: Grant only necessary permissions
- **Auditable**: Track automation actions separately
- **Revocable**: Disable without affecting user accounts

## Usage

```bash
azlin auth setup [OPTIONS]
```

## Options

| Option | Type | Description |
|--------|------|-------------|
| `-p, --profile TEXT` | Name | Authentication profile name (default: `default`) |
| `--tenant-id TEXT` | UUID | Azure Tenant ID (required) |
| `--client-id TEXT` | UUID | Service Principal Application/Client ID (required) |
| `--subscription-id TEXT` | UUID | Azure Subscription ID (required) |
| `--use-certificate` | Flag | Use certificate-based authentication |
| `--certificate-path PATH` | File | Path to certificate file (PEM format) when using cert auth |
| `-h, --help` | Flag | Show command help and exit |

## Examples

### Interactive Setup

```bash
# Interactive mode - prompts for all required information
azlin auth setup

# Follow prompts:
# - Profile name: prod
# - Tenant ID: xxx
# - Client ID: xxx
# - Subscription ID: xxx
# - Use certificate? (y/n): n
# - Set AZLIN_SP_CLIENT_SECRET environment variable
```

### Client Secret Authentication

```bash
# Non-interactive with client secret
azlin auth setup \
    --profile prod \
    --tenant-id "YOUR-TENANT-ID" \
    --client-id "YOUR-CLIENT-ID" \
    --subscription-id "YOUR-SUBSCRIPTION-ID"

# Set client secret in environment
export AZLIN_SP_CLIENT_SECRET="your-client-secret-value"

# Test authentication
azlin list --profile prod
```

### Certificate-Based Authentication

```bash
# Setup with certificate (more secure)
azlin auth setup \
    --profile prod \
    --tenant-id "YOUR-TENANT-ID" \
    --client-id "YOUR-CLIENT-ID" \
    --subscription-id "YOUR-SUBSCRIPTION-ID" \
    --use-certificate \
    --certificate-path ~/certs/sp-cert.pem

# No environment variable needed for certificates
azlin list --profile prod
```

### Multiple Profiles

```bash
# Development environment
azlin auth setup \
    --profile dev \
    --tenant-id "$DEV_TENANT_ID" \
    --client-id "$DEV_CLIENT_ID" \
    --subscription-id "$DEV_SUBSCRIPTION_ID"

# Production environment
azlin auth setup \
    --profile prod \
    --tenant-id "$PROD_TENANT_ID" \
    --client-id "$PROD_CLIENT_ID" \
    --subscription-id "$PROD_SUBSCRIPTION_ID"

# Use different profiles
azlin list --profile dev
azlin list --profile prod
```

## Prerequisites

### 1. Create Service Principal

Create an Azure service principal with required permissions:

```bash
# Create service principal with Contributor role
az ad sp create-for-rbac \
    --name "azlin-automation" \
    --role Contributor \
    --scopes /subscriptions/YOUR-SUBSCRIPTION-ID

# Output:
# {
#   "appId": "YOUR-CLIENT-ID",
#   "password": "YOUR-CLIENT-SECRET",
#   "tenant": "YOUR-TENANT-ID"
# }
```

**Important:** Save the output - the client secret cannot be retrieved later!

### 2. Assign Required Permissions

Service principal needs these permissions:
- **Virtual Machine Contributor**: Manage VMs
- **Network Contributor**: Manage network resources
- **Storage Account Contributor**: Access storage
- **Key Vault Secrets User**: Retrieve SSH keys

```bash
# Assign additional roles if needed
az role assignment create \
    --assignee YOUR-CLIENT-ID \
    --role "Key Vault Secrets User" \
    --scope /subscriptions/YOUR-SUBSCRIPTION-ID
```

### 3. Certificate Setup (Optional)

For certificate-based authentication:

```bash
# Generate certificate
openssl req -new -x509 -days 365 -keyout sp-key.pem -out sp-cert.pem -nodes

# Upload certificate to service principal
az ad sp credential reset \
    --name YOUR-CLIENT-ID \
    --cert @sp-cert.pem

# Use certificate with azlin
azlin auth setup \
    --profile prod \
    --tenant-id "$TENANT_ID" \
    --client-id "$CLIENT_ID" \
    --subscription-id "$SUBSCRIPTION_ID" \
    --use-certificate \
    --certificate-path ./sp-cert.pem
```

## Authentication Methods Comparison

### Client Secret

**Pros:**
- Simple to set up
- Easy to rotate
- Works in any environment

**Cons:**
- Secrets must be securely stored
- Can be accidentally exposed
- Requires secure secret management

**Best for:**
- Development environments
- Quick prototyping
- Environments with secret management (GitHub Secrets, etc.)

**Setup:**
```bash
azlin auth setup --profile dev --tenant-id "$T" --client-id "$C" --subscription-id "$S"
export AZLIN_SP_CLIENT_SECRET="secret-value"
```

### Certificate

**Pros:**
- More secure than secrets
- Cannot be guessed or brute-forced
- Better for compliance requirements

**Cons:**
- More complex setup
- Certificate files must be managed
- Requires certificate renewal

**Best for:**
- Production environments
- Compliance-sensitive workloads
- Long-term automation

**Setup:**
```bash
azlin auth setup --profile prod --tenant-id "$T" --client-id "$C" \
    --subscription-id "$S" --use-certificate --certificate-path ./cert.pem
```

## Configuration Storage

Auth profiles are stored in `~/.azlin/auth.toml`:

```toml
[profiles.default]
tenant_id = "YOUR-TENANT-ID"
client_id = "YOUR-CLIENT-ID"
subscription_id = "YOUR-SUBSCRIPTION-ID"
auth_method = "client_secret"  # or "certificate"

[profiles.prod]
tenant_id = "PROD-TENANT-ID"
client_id = "PROD-CLIENT-ID"
subscription_id = "PROD-SUBSCRIPTION-ID"
auth_method = "certificate"
certificate_path = "/path/to/cert.pem"
```

**Security:** Client secrets are NOT stored in config file - only via environment variables.

## CI/CD Integration

### GitHub Actions

```yaml
name: Deploy to Azure

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Setup azlin authentication
        run: |
          azlin auth setup \
            --profile prod \
            --tenant-id "${{ secrets.AZURE_TENANT_ID }}" \
            --client-id "${{ secrets.AZURE_CLIENT_ID }}" \
            --subscription-id "${{ secrets.AZURE_SUBSCRIPTION_ID }}"
        env:
          AZLIN_SP_CLIENT_SECRET: ${{ secrets.AZURE_CLIENT_SECRET }}

      - name: Deploy to VM
        run: |
          azlin connect deploy-vm -- ./deploy.sh
        env:
          AZLIN_SP_CLIENT_SECRET: ${{ secrets.AZURE_CLIENT_SECRET }}
```

### GitLab CI

```yaml
deploy:
  stage: deploy
  script:
    - azlin auth setup --profile prod --tenant-id "$TENANT_ID"
        --client-id "$CLIENT_ID" --subscription-id "$SUBSCRIPTION_ID"
    - azlin connect prod-vm -- ./deploy.sh
  variables:
    AZLIN_SP_CLIENT_SECRET: $AZURE_CLIENT_SECRET
```

### Jenkins

```groovy
pipeline {
    agent any
    environment {
        AZLIN_SP_CLIENT_SECRET = credentials('azure-client-secret')
    }
    stages {
        stage('Setup') {
            steps {
                sh '''
                    azlin auth setup \
                        --profile jenkins \
                        --tenant-id "${TENANT_ID}" \
                        --client-id "${CLIENT_ID}" \
                        --subscription-id "${SUBSCRIPTION_ID}"
                '''
            }
        }
        stage('Deploy') {
            steps {
                sh 'azlin connect deploy-vm -- ./deploy.sh'
            }
        }
    }
}
```

### Cron Job

```bash
#!/bin/bash
# /etc/cron.daily/azlin-vm-management

# Load secrets from secure location
source /etc/azlin/secrets.env

# Setup authentication
azlin auth setup \
    --profile automation \
    --tenant-id "$TENANT_ID" \
    --client-id "$CLIENT_ID" \
    --subscription-id "$SUBSCRIPTION_ID"

# Stop development VMs at night
azlin list --tag environment=dev --profile automation | \
    grep Running | while read vm _; do
    azlin stop $vm --deallocate --profile automation
done
```

## Troubleshooting

### Authentication Failed

**Symptoms:** "Authentication failed" or "Invalid credentials" error.

**Solutions:**
```bash
# Verify tenant/client/subscription IDs are correct
az login
az account show  # Check subscription ID
az ad sp show --id YOUR-CLIENT-ID  # Verify service principal exists

# Check client secret is set
echo $AZLIN_SP_CLIENT_SECRET  # Should not be empty

# Test service principal authentication directly
az login --service-principal \
    --username YOUR-CLIENT-ID \
    --password YOUR-CLIENT-SECRET \
    --tenant YOUR-TENANT-ID
```

### Permission Denied

**Symptoms:** "Insufficient permissions" or "Authorization failed" error.

**Solutions:**
```bash
# Check service principal role assignments
az role assignment list --assignee YOUR-CLIENT-ID --output table

# Assign required roles
az role assignment create \
    --assignee YOUR-CLIENT-ID \
    --role "Contributor" \
    --scope /subscriptions/YOUR-SUBSCRIPTION-ID
```

### Certificate Not Found

**Symptoms:** "Certificate file not found" or "Invalid certificate" error.

**Solutions:**
```bash
# Verify certificate file exists
ls -la ~/certs/sp-cert.pem

# Check certificate format (should be PEM)
openssl x509 -in ~/certs/sp-cert.pem -text -noout

# Re-upload certificate to service principal
az ad sp credential reset --name YOUR-CLIENT-ID --cert @sp-cert.pem
```

### Environment Variable Not Set

**Symptoms:** "AZLIN_SP_CLIENT_SECRET not set" error.

**Solutions:**
```bash
# Set environment variable
export AZLIN_SP_CLIENT_SECRET="your-secret"

# For permanent setting (add to ~/.bashrc or ~/.zshrc)
echo 'export AZLIN_SP_CLIENT_SECRET="your-secret"' >> ~/.bashrc
source ~/.bashrc

# In CI/CD, use secret management:
# GitHub: Secrets
# GitLab: CI/CD Variables
# Jenkins: Credentials
```

## Security Best Practices

### 1. Secret Management

```bash
# DO NOT commit secrets to git
echo "AZLIN_SP_CLIENT_SECRET=secret" >> .env
echo ".env" >> .gitignore

# Use secret managers
# - GitHub: Secrets
# - Azure Key Vault: az keyvault secret set
# - HashiCorp Vault: vault kv put
```

### 2. Least Privilege

```bash
# Scope service principal to specific resource group
az role assignment create \
    --assignee YOUR-CLIENT-ID \
    --role "Virtual Machine Contributor" \
    --scope /subscriptions/SUB-ID/resourceGroups/RG-NAME

# Not entire subscription
```

### 3. Certificate Rotation

```bash
# Rotate certificates regularly (e.g., annually)
openssl req -new -x509 -days 365 -keyout new-key.pem -out new-cert.pem -nodes
az ad sp credential reset --name YOUR-CLIENT-ID --cert @new-cert.pem
azlin auth setup --profile prod ... --certificate-path ./new-cert.pem
```

### 4. Audit Logging

```bash
# Enable Azure activity logs for service principal
az monitor activity-log list --caller YOUR-CLIENT-ID

# Track what automation is doing
```

## Related Commands

- [`azlin auth list`](list.md) - List configured auth profiles
- [`azlin auth show`](show.md) - Show profile details
- [`azlin auth remove`](remove.md) - Remove auth profile
- [`azlin auth test`](test.md) - Test authentication
- [`azlin context create`](../context/create.md) - Create contexts with auth profiles

## Source Code

- [azure_auth.py](https://github.com/rysweet/azlin/blob/main/src/azlin/azure_auth.py) - Authentication logic
- [auth_models.py](https://github.com/rysweet/azlin/blob/main/src/azlin/auth_models.py) - Auth configuration models
- [cli.py](https://github.com/rysweet/azlin/blob/main/src/azlin/cli.py) - CLI command definition

## See Also

- [All auth commands](index.md)
- [GitHub Runners](../../advanced/github-runners.md)
- [Security Benefits](../../bastion/security.md)
- [Azure Service Principals Documentation](https://docs.microsoft.com/azure/active-directory/develop/app-objects-and-service-principals)
