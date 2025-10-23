# Service Principal Authentication Setup Guide

Complete guide to setting up and using Azure Service Principal authentication with azlin.

## Table of Contents

- [Overview](#overview)
- [Prerequisites](#prerequisites)
- [Authentication Methods](#authentication-methods)
- [Quick Start](#quick-start)
- [Method 1: Azure CLI (Default)](#method-1-azure-cli-default)
- [Method 2: Service Principal with Client Secret](#method-2-service-principal-with-client-secret)
- [Method 3: Service Principal with Certificate](#method-3-service-principal-with-certificate)
- [Method 4: Managed Identity](#method-4-managed-identity)
- [Profile Management](#profile-management)
- [Security Best Practices](#security-best-practices)
- [Troubleshooting](#troubleshooting)
- [Examples](#examples)

## Overview

### What is Service Principal Authentication?

Service principal authentication allows azlin to authenticate with Azure using dedicated application credentials instead of user credentials. This enables:

- **Automation**: CI/CD pipelines can provision VMs without user login
- **Separation of Concerns**: Different environments (dev, staging, prod) use different credentials
- **Fine-grained Permissions**: Grant only the permissions needed for VM operations
- **Audit Trail**: Track which application performed which operations

### Why Use Service Principals?

| Scenario | Recommended Method |
|----------|-------------------|
| Local development | Azure CLI (default) |
| CI/CD pipelines | Service Principal with Secret |
| Production deployments | Service Principal with Certificate |
| Azure VM/container | Managed Identity |
| Team environments | Service Principal (shared profiles) |

### Security Philosophy

azlin implements strict security controls:

- **NO secrets in configuration files** - All secrets come from environment variables
- **Certificate permissions enforced** - Only 0600 or 0400 permissions allowed
- **UUID validation** - All Azure IDs validated to prevent injection
- **Log sanitization** - Secrets automatically redacted from logs
- **Fail-fast validation** - Invalid configurations rejected immediately

## Prerequisites

Before setting up service principal authentication, ensure you have:

1. **Azure Subscription** - Active Azure subscription with appropriate permissions
2. **Azure CLI** - Installed and updated to latest version
   ```bash
   # macOS
   brew install azure-cli

   # Linux (Ubuntu/Debian)
   curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash

   # Verify installation
   az --version
   ```

3. **azlin** - Installed via pip or uv
   ```bash
   # Install with uv (recommended)
   uv tool install azlin

   # Or with pip
   pip install azlin
   ```

4. **Permissions** - Ability to create service principals (requires Azure AD role)
   - Application Administrator
   - Or Global Administrator
   - Or custom role with `microsoft.directory/applications/create` permission

## Authentication Methods

azlin supports four authentication methods:

### 1. Azure CLI (az_cli)

**Default method** - Uses your existing Azure CLI login.

- **Pros**: Zero setup, works immediately after `az login`
- **Cons**: Tied to your user account, not suitable for automation
- **Use case**: Local development, personal projects

### 2. Service Principal with Client Secret (service_principal_secret)

Uses an application ID and secret string for authentication.

- **Pros**: Simple setup, works in any environment
- **Cons**: Secret management required, secrets can leak
- **Use case**: CI/CD pipelines, testing environments

### 3. Service Principal with Certificate (service_principal_cert)

Uses an application ID and certificate file for authentication.

- **Pros**: More secure than secrets, certificate rotation supported
- **Cons**: Certificate management overhead, file permissions critical
- **Use case**: Production environments, high-security scenarios

### 4. Managed Identity (managed_identity)

Uses Azure-managed identity (no credentials needed).

- **Pros**: No credential management, automatic rotation
- **Cons**: Only works on Azure resources (VMs, App Service, etc.)
- **Use case**: Running azlin from Azure VMs or containers

## Quick Start

Get started with service principal authentication in 3 steps:

```bash
# Step 1: Create a service principal (Azure CLI method)
az ad sp create-for-rbac --name azlin-sp --role Contributor

# Step 2: Set environment variable with the secret
export AZURE_CLIENT_SECRET="<client-secret-from-step-1>"

# Step 3: Create azlin profile
azlin auth setup
```

Follow the interactive prompts, then test:

```bash
# Test authentication
azlin auth test --profile default

# Use it with azlin commands
azlin list
```

## Method 1: Azure CLI (Default)

The simplest method - uses your existing Azure CLI credentials.

### Setup

1. **Login to Azure CLI**
   ```bash
   az login
   ```

2. **Verify login**
   ```bash
   az account show
   ```

3. **Use azlin normally**
   ```bash
   azlin list
   azlin new
   ```

### How It Works

- azlin delegates authentication to Azure CLI
- Uses tokens stored in `~/.azure/`
- No additional configuration needed
- Maintains backward compatibility with existing workflows

### When to Use

- Local development on your workstation
- Personal projects
- Quick testing and exploration
- When you're already logged in with `az login`

### Limitations

- Requires interactive login (not suitable for automation)
- Tied to your user account (no separation)
- Cannot use in headless environments (CI/CD)

## Method 2: Service Principal with Client Secret

Authenticate using an application ID and secret string.

### Step 1: Create Service Principal

Using Azure CLI (recommended):

```bash
# Create service principal with Contributor role
az ad sp create-for-rbac \
  --name azlin-automation \
  --role Contributor \
  --scopes /subscriptions/<subscription-id>

# Output:
# {
#   "appId": "12345678-1234-1234-1234-123456789abc",
#   "displayName": "azlin-automation",
#   "password": "your-client-secret-here",
#   "tenant": "87654321-4321-4321-4321-cba987654321"
# }
```

**IMPORTANT**: Save the password (client secret) immediately - it won't be shown again!

Using Azure Portal:

1. Navigate to Azure Active Directory > App registrations
2. Click "New registration"
3. Name: `azlin-automation`, click "Register"
4. Note the "Application (client) ID" and "Directory (tenant) ID"
5. Go to "Certificates & secrets" > "New client secret"
6. Description: `azlin-secret`, Expiration: 12 months
7. Click "Add" and copy the secret value immediately

### Step 2: Assign Permissions

Grant the service principal permission to manage VMs:

```bash
# Assign Contributor role to resource group
az role assignment create \
  --assignee <app-id> \
  --role Contributor \
  --scope /subscriptions/<subscription-id>/resourceGroups/<resource-group>

# Or for entire subscription (use with caution)
az role assignment create \
  --assignee <app-id> \
  --role Contributor \
  --scope /subscriptions/<subscription-id>
```

### Step 3: Configure Environment Variable

**CRITICAL**: Never put the client secret in config files or commit it to version control.

```bash
# Set environment variable (temporary)
export AZURE_CLIENT_SECRET="your-client-secret-here"

# Make it permanent (add to ~/.bashrc or ~/.zshrc)
echo 'export AZURE_CLIENT_SECRET="your-client-secret-here"' >> ~/.bashrc
source ~/.bashrc

# Verify it's set
echo $AZURE_CLIENT_SECRET
```

**Security Note**: Consider using a secrets manager (Azure Key Vault, HashiCorp Vault) in production.

### Step 4: Create azlin Profile

```bash
azlin auth setup --profile production
```

Interactive prompts:

```
Choose authentication method:
  1. Azure CLI (default)
  2. Service principal with client secret
  3. Service principal with certificate
  4. Managed identity

Selection [1]: 2

Service Principal with Client Secret
----------------------------------------
Enter tenant ID (UUID): 87654321-4321-4321-4321-cba987654321
Enter client ID (UUID): 12345678-1234-1234-1234-123456789abc
Enter subscription ID (UUID): <your-subscription-id>

Profile name [default]: production

✓ Profile 'production' created

Note: Set AZURE_CLIENT_SECRET environment variable to use this profile

To test: azlin auth test --profile production
```

### Step 5: Test Authentication

```bash
# Test the profile
azlin auth test --profile production

# Output:
# Testing Azure authentication...
#
# Using profile: production
# Method: service_principal_secret
#
# ✓ Authentication successful
#
# Credentials:
#   Method: service_principal_secret
#   Tenant ID: 87654321-4321-4321-4321-cba987654321
#   Subscription ID: <your-subscription-id>
```

### Step 6: Use with azlin Commands

```bash
# List VMs using the profile
AZLIN_PROFILE=production azlin list

# Or set as default
export AZLIN_PROFILE=production
azlin list
azlin new --name my-vm
```

## Method 3: Service Principal with Certificate

Authenticate using an application ID and certificate file (more secure than secrets).

### Step 1: Generate Certificate

Generate a self-signed certificate for authentication:

```bash
# Generate private key and certificate (valid for 1 year)
openssl req -x509 -newkey rsa:4096 -keyout azlin-cert.pem -out azlin-cert.pem \
  -days 365 -nodes -subj "/CN=azlin-automation"

# Set correct permissions (REQUIRED)
chmod 600 azlin-cert.pem

# Verify permissions
ls -l azlin-cert.pem
# Output should show: -rw------- (600)
```

**Security Requirements**:
- Certificate file MUST have 0600 or 0400 permissions
- Store in secure location (e.g., `~/.azlin/certs/`)
- Never commit to version control
- Rotate certificates before expiration

### Step 2: Create Service Principal with Certificate

```bash
# Create service principal with certificate
az ad sp create-for-rbac \
  --name azlin-automation-cert \
  --role Contributor \
  --scopes /subscriptions/<subscription-id> \
  --cert @azlin-cert.pem

# Output:
# {
#   "appId": "12345678-1234-1234-1234-123456789abc",
#   "displayName": "azlin-automation-cert",
#   "tenant": "87654321-4321-4321-4321-cba987654321"
# }
```

Using Azure Portal:

1. Create App Registration (see Method 2)
2. Go to "Certificates & secrets" > "Certificates" tab
3. Click "Upload certificate"
4. Upload `azlin-cert.pem`
5. Note the thumbprint

### Step 3: Store Certificate Securely

```bash
# Create certs directory
mkdir -p ~/.azlin/certs
chmod 700 ~/.azlin/certs

# Move certificate to secure location
mv azlin-cert.pem ~/.azlin/certs/
chmod 600 ~/.azlin/certs/azlin-cert.pem

# Verify permissions
ls -la ~/.azlin/certs/
# Directory should be: drwx------ (700)
# Certificate should be: -rw------- (600)
```

### Step 4: Create azlin Profile

```bash
azlin auth setup --profile production-cert
```

Interactive prompts:

```
Choose authentication method:
  1. Azure CLI (default)
  2. Service principal with client secret
  3. Service principal with certificate
  4. Managed identity

Selection [1]: 3

Service Principal with Certificate
----------------------------------------
Enter tenant ID (UUID): 87654321-4321-4321-4321-cba987654321
Enter client ID (UUID): 12345678-1234-1234-1234-123456789abc
Enter certificate file path: ~/.azlin/certs/azlin-cert.pem
Enter subscription ID (UUID): <your-subscription-id>

Profile name [default]: production-cert

✓ Profile 'production-cert' created

Note: Ensure certificate file is accessible at: ~/.azlin/certs/azlin-cert.pem

To test: azlin auth test --profile production-cert
```

### Step 5: Test Authentication

```bash
azlin auth test --profile production-cert
```

### Certificate Expiration Management

Monitor certificate expiration:

```bash
# Check certificate expiration
openssl x509 -in ~/.azlin/certs/azlin-cert.pem -noout -enddate

# azlin automatically warns if certificate expires within 30 days
azlin auth test --profile production-cert
# Warning: Certificate expires soon (in 25 days). Renewal recommended.
```

Rotate certificates before expiration:

```bash
# Generate new certificate
openssl req -x509 -newkey rsa:4096 -keyout azlin-cert-new.pem \
  -out azlin-cert-new.pem -days 365 -nodes -subj "/CN=azlin-automation"
chmod 600 azlin-cert-new.pem

# Upload to Azure Portal or use Azure CLI
az ad app credential reset --id <app-id> --cert @azlin-cert-new.pem

# Update profile to use new certificate
# (Edit ~/.azlin/profiles/production-cert.toml or recreate profile)

# Test new certificate
azlin auth test --profile production-cert
```

## Method 4: Managed Identity

Authenticate using Azure-managed identity (no credentials needed).

### What is Managed Identity?

Managed Identity is an Azure feature that provides Azure services with an automatically managed identity in Azure AD. No credentials are stored or managed by you.

**Types**:
- **System-assigned**: Tied to a single Azure resource (VM, App Service, etc.)
- **User-assigned**: Can be used by multiple Azure resources

### When to Use

- Running azlin on an Azure VM
- Running azlin in Azure Container Instances
- Running azlin in Azure App Service
- Running azlin in Azure Functions

### Setup on Azure VM

#### Step 1: Enable Managed Identity on VM

Using Azure Portal:

1. Navigate to your VM > Identity
2. System assigned tab > Status: On
3. Click "Save"
4. Note the Object (principal) ID

Using Azure CLI:

```bash
# Enable system-assigned managed identity
az vm identity assign --name <vm-name> --resource-group <resource-group>

# Output:
# {
#   "principalId": "12345678-1234-1234-1234-123456789abc",
#   "tenantId": "87654321-4321-4321-4321-cba987654321",
#   "type": "SystemAssigned"
# }
```

#### Step 2: Assign Permissions

Grant the managed identity permission to manage resources:

```bash
# Get the principal ID from step 1
PRINCIPAL_ID=$(az vm identity show --name <vm-name> --resource-group <resource-group> --query principalId -o tsv)

# Assign Contributor role
az role assignment create \
  --assignee $PRINCIPAL_ID \
  --role Contributor \
  --scope /subscriptions/<subscription-id>
```

#### Step 3: Create azlin Profile on the VM

SSH into the VM and create a managed identity profile:

```bash
# SSH into the VM
ssh azureuser@<vm-ip>

# Install azlin (if not already installed)
pip install azlin

# Create managed identity profile
azlin auth setup --profile managed
```

Interactive prompts:

```
Choose authentication method:
  1. Azure CLI (default)
  2. Service principal with client secret
  3. Service principal with certificate
  4. Managed identity

Selection [1]: 4

Managed Identity
----------------------------------------
Leave client ID empty for system-assigned managed identity.
Enter client ID (UUID) for user-assigned MI:
Enter subscription ID (UUID): <your-subscription-id>

Profile name [default]: managed

✓ Profile 'managed' created

Note: This profile will only work on Azure resources with managed identity enabled

To test: azlin auth test --profile managed
```

#### Step 4: Test Authentication

```bash
azlin auth test --profile managed

# Use it
azlin list
azlin new --name test-vm
```

### User-Assigned Managed Identity

For user-assigned managed identity:

```bash
# Create user-assigned identity
az identity create --name azlin-identity --resource-group <resource-group>

# Get the client ID
CLIENT_ID=$(az identity show --name azlin-identity --resource-group <resource-group> --query clientId -o tsv)

# Assign to VM
az vm identity assign \
  --name <vm-name> \
  --resource-group <resource-group> \
  --identities azlin-identity

# Create profile with client ID
azlin auth setup --profile managed-user
# Enter the client ID when prompted
```

## Profile Management

Manage authentication profiles with the `azlin auth` command group.

### List All Profiles

```bash
azlin auth list
```

Output:

```
Authentication Profiles
================================================================================

production
  Method: service_principal_secret
  Tenant ID: 87654321-4321-4321-4321-cba987654321
  Client ID: 12345678-1234-1234-1234-123456789abc
  Subscription ID: <subscription-id>
  Created: 2025-10-15 14:30:00
  Last Used: 2025-10-23 09:15:00

production-cert
  Method: service_principal_cert
  Tenant ID: 87654321-4321-4321-4321-cba987654321
  Client ID: 12345678-1234-1234-1234-123456789abc
  Subscription ID: <subscription-id>
  Created: 2025-10-20 10:45:00
  Last Used: Never

Total: 2 profile(s)
```

### Show Profile Details

```bash
azlin auth show --profile production
```

Output:

```
Profile: production
================================================================================

Authentication Method: service_principal_secret

Configuration:
  Tenant ID: 87654321-4321-4321-4321-cba987654321
  Client ID: 12345678-1234-1234-1234-123456789abc
  Subscription ID: <subscription-id>
  Client Secret: (from AZURE_CLIENT_SECRET environment variable)

Note: Set AZURE_CLIENT_SECRET environment variable before use
```

### Test Profile Authentication

```bash
azlin auth test --profile production
```

Output:

```
Testing Azure authentication...

Using profile: production
Method: service_principal_secret

✓ Authentication successful

Credentials:
  Method: service_principal_secret
  Tenant ID: 87654321-4321-4321-4321-cba987654321
  Subscription ID: <subscription-id>
```

### Delete Profile

```bash
# With confirmation prompt
azlin auth delete production

# Skip confirmation
azlin auth delete production --force
```

### Using Profiles

Three ways to specify which profile to use:

**1. Environment Variable (Recommended)**

```bash
export AZLIN_PROFILE=production
azlin list
azlin new
```

**2. Per-Command**

```bash
AZLIN_PROFILE=production azlin list
```

**3. Command-Line Option**

```bash
azlin --profile production list
azlin --profile production new
```

### Profile Storage

Profiles are stored at `~/.azlin/profiles/<profile-name>.toml`:

```bash
ls -la ~/.azlin/profiles/
# -rw------- 1 user user  256 Oct 23 14:30 production.toml
# -rw------- 1 user user  312 Oct 20 10:45 production-cert.toml
```

**Security**: Profile files have 0600 permissions (owner read/write only).

## Security Best Practices

### P0 Security Controls

azlin implements strict security controls:

1. **NO Secrets in Config Files**
   - Client secrets MUST be in `AZURE_CLIENT_SECRET` environment variable
   - Profile files validated to reject embedded secrets
   - Configuration changes that include secrets are rejected

2. **Certificate Permissions**
   - Only 0600 or 0400 permissions allowed
   - azlin validates permissions before use
   - Fails fast if permissions are incorrect

3. **UUID Validation**
   - All Azure IDs validated as proper UUIDs
   - Prevents injection attacks
   - Clear error messages for invalid formats

4. **Log Sanitization**
   - All secrets automatically redacted from logs
   - Bearer tokens, client secrets, certificates masked
   - Safe for debugging and audit logs

### Secret Management

**Environment Variables**

```bash
# WRONG - Never commit secrets to files
# config.toml:
# client_secret = "my-secret"

# RIGHT - Use environment variables
export AZURE_CLIENT_SECRET="my-secret"
```

**Secrets Managers (Production)**

Use Azure Key Vault or similar:

```bash
# Fetch secret from Key Vault
export AZURE_CLIENT_SECRET=$(az keyvault secret show \
  --vault-name my-vault \
  --name azlin-client-secret \
  --query value -o tsv)

# Use with azlin
azlin list
```

**CI/CD Pipelines**

Use pipeline secrets:

```yaml
# GitHub Actions
- name: Run azlin
  env:
    AZURE_CLIENT_SECRET: ${{ secrets.AZURE_CLIENT_SECRET }}
  run: |
    azlin list
```

### Certificate Security

**Permissions**

```bash
# WRONG - World-readable certificate
chmod 644 azlin-cert.pem  # DON'T DO THIS

# RIGHT - Owner-only read/write
chmod 600 azlin-cert.pem
```

**Storage**

```bash
# Store in secure directory
mkdir -p ~/.azlin/certs
chmod 700 ~/.azlin/certs
mv cert.pem ~/.azlin/certs/
chmod 600 ~/.azlin/certs/cert.pem
```

**Expiration Monitoring**

```bash
# Check expiration regularly
openssl x509 -in ~/.azlin/certs/azlin-cert.pem -noout -enddate

# Set up monitoring (cron job)
0 9 * * * /usr/bin/openssl x509 -in ~/.azlin/certs/azlin-cert.pem -checkend 2592000 && echo "Certificate expires in 30 days" | mail -s "Certificate Alert" admin@example.com
```

**Rotation**

Rotate certificates every 6-12 months:

1. Generate new certificate
2. Upload to Azure
3. Update azlin profile
4. Test authentication
5. Delete old certificate

### Principle of Least Privilege

Grant only the permissions needed:

```bash
# AVOID - Contributor on entire subscription
az role assignment create \
  --assignee <app-id> \
  --role Contributor \
  --scope /subscriptions/<subscription-id>

# PREFER - Contributor on specific resource group
az role assignment create \
  --assignee <app-id> \
  --role Contributor \
  --scope /subscriptions/<subscription-id>/resourceGroups/azlin-vms

# BEST - Custom role with minimal permissions
az role definition create --role-definition '{
  "Name": "azlin VM Manager",
  "Description": "Can manage VMs for azlin",
  "Actions": [
    "Microsoft.Compute/virtualMachines/*",
    "Microsoft.Network/networkInterfaces/*",
    "Microsoft.Network/publicIPAddresses/*"
  ],
  "AssignableScopes": ["/subscriptions/<subscription-id>/resourceGroups/azlin-vms"]
}'
```

### Audit and Monitoring

Track authentication usage:

```bash
# View Azure AD sign-in logs
az monitor activity-log list \
  --resource-type Microsoft.Compute/virtualMachines \
  --start-time 2025-10-01

# Check service principal usage
azlin auth list
# Review "Last Used" timestamps
```

## Troubleshooting

### Common Issues and Solutions

#### "No Azure credentials available"

**Symptoms**: Error when running azlin commands

```
Error: No Azure credentials available. Please run: az login
```

**Solutions**:

1. Check if logged in to Azure CLI:
   ```bash
   az account show
   # If error, run: az login
   ```

2. Verify environment variable is set:
   ```bash
   echo $AZURE_CLIENT_SECRET
   # Should print your secret, not empty
   ```

3. Verify profile exists and is valid:
   ```bash
   azlin auth list
   azlin auth test --profile <profile-name>
   ```

#### "Invalid UUID format"

**Symptoms**: Error when creating profile

```
Error: Invalid tenant_id format: must be a valid UUID
```

**Solution**: Ensure IDs are proper UUIDs (8-4-4-4-12 format)

```bash
# WRONG
tenant_id: "abc123"

# RIGHT
tenant_id: "12345678-1234-1234-1234-123456789abc"
```

Find your IDs:

```bash
# Tenant ID
az account show --query tenantId -o tsv

# Subscription ID
az account show --query id -o tsv

# Service principal client ID
az ad sp list --display-name azlin-automation --query [0].appId -o tsv
```

#### "Certificate validation failed"

**Symptoms**: Error when using certificate authentication

```
Error: Certificate validation failed: Invalid certificate permissions: 0o644. Must be exactly 0600 or 0400 for security.
```

**Solution**: Fix certificate permissions

```bash
# Check current permissions
ls -l ~/.azlin/certs/azlin-cert.pem

# Fix permissions
chmod 600 ~/.azlin/certs/azlin-cert.pem

# Verify
ls -l ~/.azlin/certs/azlin-cert.pem
# Should show: -rw-------
```

#### "Profile contains secrets"

**Symptoms**: Error when creating profile

```
Error: SECURITY VIOLATION: Profile contains secrets that cannot be stored in profiles.
Fields with secrets: client_secret
```

**Solution**: Remove client_secret from profile, use environment variable

```bash
# Don't put secret in profile
# Instead, export as environment variable
export AZURE_CLIENT_SECRET="your-secret"

# Then create profile without secret
azlin auth setup --profile production
```

#### "Authentication failed"

**Symptoms**: Authentication test fails

```
Error: Failed to authenticate with service principal: AADSTS7000215: Invalid client secret provided.
```

**Solutions**:

1. Verify client secret is correct:
   ```bash
   echo $AZURE_CLIENT_SECRET
   ```

2. Check if secret has expired:
   ```bash
   # In Azure Portal: App registrations > Certificates & secrets
   # Check expiration date of client secret
   ```

3. Regenerate secret if expired:
   ```bash
   az ad sp credential reset --id <app-id>
   # Update AZURE_CLIENT_SECRET with new secret
   ```

#### "Certificate has expired"

**Symptoms**: Warning or error about certificate expiration

```
Warning: Certificate has expired (expired 5 days ago)
```

**Solution**: Rotate certificate

```bash
# Generate new certificate
openssl req -x509 -newkey rsa:4096 -keyout azlin-cert-new.pem \
  -out azlin-cert-new.pem -days 365 -nodes -subj "/CN=azlin-automation"
chmod 600 azlin-cert-new.pem

# Upload to Azure
az ad app credential reset --id <app-id> --cert @azlin-cert-new.pem

# Update profile
# Edit ~/.azlin/profiles/<profile>.toml
# Or recreate profile with new certificate path
```

#### "Permission denied" Errors

**Symptoms**: azlin can authenticate but cannot perform operations

```
Error: Insufficient permissions to create VM
```

**Solutions**:

1. Check assigned roles:
   ```bash
   az role assignment list --assignee <app-id> --all
   ```

2. Assign Contributor role:
   ```bash
   az role assignment create \
     --assignee <app-id> \
     --role Contributor \
     --scope /subscriptions/<subscription-id>/resourceGroups/<resource-group>
   ```

3. Verify service principal has correct permissions:
   ```bash
   # List required permissions for azlin operations:
   # - Microsoft.Compute/virtualMachines/*
   # - Microsoft.Network/networkInterfaces/*
   # - Microsoft.Network/publicIPAddresses/*
   # - Microsoft.Storage/storageAccounts/* (if using NFS)
   ```

### Debug Mode

Enable verbose logging for troubleshooting:

```bash
# Set log level
export AZLIN_LOG_LEVEL=DEBUG

# Run command
azlin auth test --profile production

# Check logs
cat ~/.azlin/logs/azlin.log
```

## Examples

### Example 1: Development and Production Profiles

Set up separate profiles for dev and production:

```bash
# Development profile (using Azure CLI)
az login
azlin auth setup --profile dev
# Select: 1 (Azure CLI)

# Production profile (using service principal)
export AZURE_CLIENT_SECRET="<prod-secret>"
azlin auth setup --profile prod
# Select: 2 (Service principal with client secret)
# Enter prod tenant/client IDs

# Use dev profile
export AZLIN_PROFILE=dev
azlin list
azlin new --name dev-vm

# Switch to prod profile
export AZLIN_PROFILE=prod
azlin list
azlin new --name prod-vm
```

### Example 2: CI/CD Pipeline

GitHub Actions workflow using service principal:

```yaml
name: Deploy VM

on:
  push:
    branches: [main]

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install azlin
        run: pip install azlin

      - name: Create auth profile
        env:
          AZURE_CLIENT_SECRET: ${{ secrets.AZURE_CLIENT_SECRET }}
        run: |
          # Create profile non-interactively
          mkdir -p ~/.azlin/profiles
          cat > ~/.azlin/profiles/ci.toml << EOF
          auth_method = "service_principal_secret"
          tenant_id = "${{ secrets.AZURE_TENANT_ID }}"
          client_id = "${{ secrets.AZURE_CLIENT_ID }}"
          subscription_id = "${{ secrets.AZURE_SUBSCRIPTION_ID }}"

          [metadata]
          created_at = "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
          EOF
          chmod 600 ~/.azlin/profiles/ci.toml

      - name: Test authentication
        env:
          AZURE_CLIENT_SECRET: ${{ secrets.AZURE_CLIENT_SECRET }}
        run: azlin auth test --profile ci

      - name: Provision VM
        env:
          AZURE_CLIENT_SECRET: ${{ secrets.AZURE_CLIENT_SECRET }}
          AZLIN_PROFILE: ci
        run: |
          azlin new --name ci-vm-${{ github.run_number }} \
            --repo https://github.com/${{ github.repository }}
```

### Example 3: Multi-Environment Setup

Manage dev, staging, and production environments:

```bash
# Create directory for environment configs
mkdir -p ~/.azlin/envs

# Dev environment
cat > ~/.azlin/envs/dev.env << 'EOF'
export AZLIN_PROFILE=dev
export AZURE_RESOURCE_GROUP=azlin-dev
export AZURE_REGION=eastus
EOF

# Staging environment
cat > ~/.azlin/envs/staging.env << 'EOF'
export AZLIN_PROFILE=staging
export AZURE_CLIENT_SECRET="<staging-secret>"
export AZURE_RESOURCE_GROUP=azlin-staging
export AZURE_REGION=eastus
EOF

# Production environment
cat > ~/.azlin/envs/prod.env << 'EOF'
export AZLIN_PROFILE=production
export AZURE_CLIENT_SECRET="<prod-secret>"
export AZURE_RESOURCE_GROUP=azlin-prod
export AZURE_REGION=westus2
EOF

# Usage
source ~/.azlin/envs/dev.env
azlin list

source ~/.azlin/envs/prod.env
azlin list
```

### Example 4: Certificate-Based Authentication

Complete workflow for certificate authentication:

```bash
# Step 1: Generate certificate
openssl req -x509 -newkey rsa:4096 -keyout azlin-prod.pem \
  -out azlin-prod.pem -days 365 -nodes \
  -subj "/CN=azlin-production/O=MyCompany/C=US"

# Step 2: Store securely
mkdir -p ~/.azlin/certs
mv azlin-prod.pem ~/.azlin/certs/
chmod 600 ~/.azlin/certs/azlin-prod.pem

# Step 3: Create service principal
az ad sp create-for-rbac \
  --name azlin-prod-cert \
  --role Contributor \
  --scopes /subscriptions/<sub-id> \
  --cert @~/.azlin/certs/azlin-prod.pem

# Step 4: Create profile
azlin auth setup --profile production
# Select: 3 (Service principal with certificate)
# Enter tenant ID, client ID, cert path

# Step 5: Test
azlin auth test --profile production

# Step 6: Use it
export AZLIN_PROFILE=production
azlin list
azlin new --name prod-vm
```

### Example 5: Managed Identity on Azure VM

Set up azlin on an Azure VM with managed identity:

```bash
# On your local machine: Enable managed identity on VM
az vm identity assign --name my-vm --resource-group my-rg

# Get principal ID
PRINCIPAL_ID=$(az vm identity show --name my-vm --resource-group my-rg --query principalId -o tsv)

# Assign permissions
az role assignment create \
  --assignee $PRINCIPAL_ID \
  --role Contributor \
  --scope /subscriptions/<subscription-id>

# SSH into the VM
ssh azureuser@<vm-ip>

# On the VM: Install azlin
pip install azlin

# Create managed identity profile
azlin auth setup --profile managed
# Select: 4 (Managed identity)
# Leave client ID empty (system-assigned)
# Enter subscription ID

# Test authentication
azlin auth test --profile managed

# Use azlin normally
azlin list
azlin new --name nested-vm
```

### Example 6: Automated Certificate Rotation

Script to rotate certificates before expiration:

```bash
#!/bin/bash
# rotate-cert.sh - Rotate Azure authentication certificate

set -e

CERT_PATH="$HOME/.azlin/certs/azlin-prod.pem"
PROFILE_NAME="production"
APP_ID="12345678-1234-1234-1234-123456789abc"

# Check if certificate expires within 30 days
if ! openssl x509 -in "$CERT_PATH" -checkend 2592000 > /dev/null; then
    echo "Certificate expires soon, rotating..."

    # Generate new certificate
    NEW_CERT="$HOME/.azlin/certs/azlin-prod-new.pem"
    openssl req -x509 -newkey rsa:4096 -keyout "$NEW_CERT" \
        -out "$NEW_CERT" -days 365 -nodes \
        -subj "/CN=azlin-production/O=MyCompany/C=US"
    chmod 600 "$NEW_CERT"

    # Upload to Azure
    az ad app credential reset --id "$APP_ID" --cert "@$NEW_CERT"

    # Update profile
    sed -i "s|client_certificate_path = \".*\"|client_certificate_path = \"$NEW_CERT\"|" \
        "$HOME/.azlin/profiles/$PROFILE_NAME.toml"

    # Test new certificate
    if azlin auth test --profile "$PROFILE_NAME"; then
        echo "Certificate rotated successfully"
        # Backup old certificate
        mv "$CERT_PATH" "$CERT_PATH.old"
        mv "$NEW_CERT" "$CERT_PATH"
        echo "Old certificate backed up to: $CERT_PATH.old"
    else
        echo "ERROR: New certificate authentication failed"
        exit 1
    fi
else
    echo "Certificate is still valid"
fi
```

Run this script monthly via cron:

```bash
# Add to crontab
crontab -e

# Run on 1st of every month at 2 AM
0 2 1 * * /path/to/rotate-cert.sh >> /var/log/azlin-cert-rotation.log 2>&1
```

---

## Additional Resources

- [Azure Service Principal Documentation](https://docs.microsoft.com/en-us/azure/active-directory/develop/app-objects-and-service-principals)
- [Azure RBAC Documentation](https://docs.microsoft.com/en-us/azure/role-based-access-control/overview)
- [Azure Managed Identity Documentation](https://docs.microsoft.com/en-us/azure/active-directory/managed-identities-azure-resources/overview)
- [Azure Key Vault for Secrets Management](https://docs.microsoft.com/en-us/azure/key-vault/)

## Support

For issues or questions:

- GitHub Issues: [https://github.com/rysweet/azlin/issues](https://github.com/rysweet/azlin/issues)
- Documentation: [https://github.com/rysweet/azlin/tree/main/docs](https://github.com/rysweet/azlin/tree/main/docs)
