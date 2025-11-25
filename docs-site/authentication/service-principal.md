# Service Principal Setup


**Version:** 1.0
**Last Updated:** 2025-10-23
**Status:** Production Ready

---

## Overview

This guide provides comprehensive setup instructions for configuring service principal authentication in azlin. Service principals enable automated, non-interactive Azure authentication for CI/CD pipelines, automation scripts, and team environments without requiring user credentials.

**What is Service Principal Authentication?**

A service principal is an identity created for use with applications, hosted services, and automated tools to access Azure resources. Unlike user authentication (Azure CLI), service principals:
- Work without interactive login
- Support certificate-based authentication for enhanced security
- Can be restricted to specific permissions and subscriptions
- Are ideal for automation and CI/CD pipelines

**azlin Authentication Methods:**

azlin supports 4 authentication methods with automatic fallback:

1. **Service Principal with Certificate** (highest security)
2. **Service Principal with Client Secret** (secure with proper secret management)
3. **Managed Identity** (for Azure-hosted workloads)
4. **Azure CLI** (default, backward compatible)

---

## Prerequisites

Before setting up service principal authentication, ensure you have:

### Required Tools
- **Azure subscription** with permissions to create service principals
- **Azure CLI** installed (`az` command)
- **azlin** installed (version 2.1+)
- **Python 3.11+** (for azlin)

### For Certificate-Based Authentication (Optional)
- **OpenSSL** for generating certificates
- **Azure Key Vault** (optional, for certificate storage)

### Installation Check

```bash
# Verify installations
az --version
azlin --version
python --version

# Login to Azure (if not already authenticated)
az login
```

---

## Authentication Methods

### Method 1: Azure CLI (Default)

**How it works:**
Uses your existing Azure CLI credentials (`az login`). No additional configuration required.

**When to use:**
- Local development
- Quick prototyping
- Personal projects
- When you're already logged in with `az login`

**Setup steps:**

```bash
# Login with Azure CLI
az login

# Use azlin normally (no profile needed)
azlin list
azlin new
```

**Benefits:**
- Zero configuration
- Seamless user experience
- Works out of the box

**Limitations:**
- Requires interactive login
- Not suitable for CI/CD
- Cannot be automated

---

### Method 2: Service Principal with Client Secret

**How it works:**
Uses an application identity (service principal) with a password (client secret) to authenticate. The secret is stored in environment variables, never in config files.

**When to use:**
- CI/CD pipelines (GitHub Actions, Azure DevOps)
- Automation scripts
- Shared development environments
- Non-interactive workflows

**Security considerations:**
- Client secrets can be compromised if leaked
- Secrets should be rotated regularly
- Use certificate-based auth when possible for production

#### Step-by-Step Setup

**Step 1: Create Service Principal in Azure**

Using Azure CLI (recommended):

```bash
# Create service principal with Contributor role
az ad sp create-for-rbac \
  --name "azlin-automation" \
  --role Contributor \
  --scopes /subscriptions/{YOUR-SUBSCRIPTION-ID}

# Output includes:
# {
#   "appId": "12345678-1234-1234-1234-123456789abc",      # Use as CLIENT_ID
#   "displayName": "azlin-automation",
#   "password": "your-secret-value-here",                 # Use as CLIENT_SECRET
#   "tenant": "87654321-4321-4321-4321-cba987654321"     # Use as TENANT_ID
# }
```

Using Azure Portal:

1. Navigate to **Azure Active Directory** → **App registrations**
2. Click **"New registration"**
3. Name: `azlin-automation`
4. Click **"Register"**
5. Note the **Application (client) ID** and **Directory (tenant) ID**
6. Go to **"Certificates & secrets"** → **"New client secret"**
7. Description: `azlin-secret`, Expires: 12 months
8. Click **"Add"** and copy the secret value (shown only once!)

**Step 2: Grant Required Permissions**

Assign the service principal access to your subscription or resource groups:

```bash
# Grant Contributor role to subscription
az role assignment create \
  --assignee {CLIENT-ID} \
  --role Contributor \
  --scope /subscriptions/{SUBSCRIPTION-ID}

# Or grant access to specific resource group
az role assignment create \
  --assignee {CLIENT-ID} \
  --role Contributor \
  --scope /subscriptions/{SUBSCRIPTION-ID}/resourceGroups/{RESOURCE-GROUP}
```

**Required permissions:**
- **Subscription level:** Reader (minimum), Contributor (recommended for VM operations)
- **Resource Group level:** Contributor (for creating/managing VMs)
- **Key Vault** (if used): Key Vault Secrets User

**Step 3: Configure azlin Profile**

Use the interactive setup wizard:

```bash
# Interactive setup
azlin auth setup

# You'll be prompted for:
# - Azure Tenant ID: 87654321-4321-4321-4321-cba987654321
# - Azure Client ID: 12345678-1234-1234-1234-123456789abc
# - Azure Subscription ID: abcdef12-3456-7890-abcd-ef1234567890
# - Use certificate? [y/N]: N
```

Or non-interactive setup:

```bash
azlin auth setup --profile prod \
  --tenant-id "87654321-4321-4321-4321-cba987654321" \
  --client-id "12345678-1234-1234-1234-123456789abc" \
  --subscription-id "abcdef12-3456-7890-abcd-ef1234567890"
```

**Step 4: Set Client Secret Environment Variable**

Set the client secret in your environment (NEVER store in config files):

```bash
# Set client secret
export AZURE_CLIENT_SECRET="your-secret-value-here"

# Or use azlin-specific variable
export AZLIN_SP_CLIENT_SECRET="your-secret-value-here"

# Make it permanent (add to ~/.bashrc or ~/.zshrc)
echo 'export AZURE_CLIENT_SECRET="your-secret-value-here"' >> ~/.bashrc
source ~/.bashrc
```

For CI/CD environments (GitHub Actions example):

```yaml
# .github/workflows/azure.yml
name: Azure Deployment

env:
  AZURE_TENANT_ID: ${{ secrets.AZURE_TENANT_ID }}
  AZURE_CLIENT_ID: ${{ secrets.AZURE_CLIENT_ID }}
  AZURE_CLIENT_SECRET: ${{ secrets.AZURE_CLIENT_SECRET }}

jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - name: Deploy with azlin
        run: |
          azlin --auth-profile prod list
```

**Step 5: Test Authentication**

```bash
# Test default profile
azlin auth test

# Test specific profile
azlin auth test --profile prod

# Test with subscription validation
azlin auth test --profile prod --subscription-id "abcdef12-3456-7890-abcd-ef1234567890"
```

Expected output:

```
Testing authentication profile: prod

Profile details:
  Client ID: 12345678-1234-1234-1234-123456789abc
  Tenant ID: 87654321-4321-4321-4321-cba987654321
  Subscription ID: abcdef12-3456-7890-abcd-ef1234567890
  Auth method: client_secret

Validating credentials...
✓ Credentials valid

Testing Azure authentication...
✓ Authentication successful!

  Authenticated as:
    Tenant: 87654321-4321-4321-4321-cba987654321
    Subscription: Production Subscription
    ID: abcdef12-3456-7890-abcd-ef1234567890
```

---

### Method 3: Service Principal with Certificate

**How it works:**
Uses a certificate file (.pem) instead of a password for authentication. This provides enhanced security through public-key cryptography.

**When to use:**
- Production environments
- High-security requirements
- Long-term automation
- When enhanced security is required

**Security benefits:**
- Cannot be compromised through password leaks
- Supports hardware security modules (HSM)
- Automatic expiration enforcement
- Stronger audit trail

#### Step-by-Step Setup

**Step 1: Generate Certificate**

Using OpenSSL (self-signed certificate):

```bash
# Generate private key and certificate
openssl req -x509 -newkey rsa:4096 -keyout sp-key.pem -out sp-cert.pem -days 365 -nodes \
  -subj "/CN=azlin-service-principal"

# Combine key and cert into single PEM file
cat sp-key.pem sp-cert.pem > azlin-sp.pem

# Clean up separate files
rm sp-key.pem sp-cert.pem

# Set secure permissions (REQUIRED)
chmod 600 azlin-sp.pem

# Move to secure location
mkdir -p ~/.azlin/certs
mv azlin-sp.pem ~/.azlin/certs/
```

Using Azure Key Vault (recommended for production):

```bash
# Create certificate in Key Vault
az keyvault certificate create \
  --vault-name "your-keyvault" \
  --name "azlin-sp-cert" \
  --policy "$(az keyvault certificate get-default-policy)"

# Download certificate
az keyvault secret download \
  --vault-name "your-keyvault" \
  --name "azlin-sp-cert" \
  --file ~/.azlin/certs/azlin-sp.pem

# Set secure permissions
chmod 600 ~/.azlin/certs/azlin-sp.pem
```

**Step 2: Create Service Principal with Certificate**

```bash
# Create service principal with certificate
az ad sp create-for-rbac \
  --name "azlin-automation-cert" \
  --role Contributor \
  --scopes /subscriptions/{SUBSCRIPTION-ID} \
  --cert @~/.azlin/certs/azlin-sp.pem

# Output includes:
# {
#   "appId": "12345678-1234-1234-1234-123456789abc",      # Use as CLIENT_ID
#   "displayName": "azlin-automation-cert",
#   "tenant": "87654321-4321-4321-4321-cba987654321"     # Use as TENANT_ID
# }
```

Or upload certificate to existing service principal:

```bash
# Upload certificate to existing service principal
az ad sp credential reset \
  --id {CLIENT-ID} \
  --cert @~/.azlin/certs/azlin-sp.pem
```

**Step 3: Configure azlin Profile**

```bash
# Interactive setup
azlin auth setup --profile prod

# You'll be prompted for:
# - Azure Tenant ID: 87654321-4321-4321-4321-cba987654321
# - Azure Client ID: 12345678-1234-1234-1234-123456789abc
# - Azure Subscription ID: abcdef12-3456-7890-abcd-ef1234567890
# - Use certificate? [y/N]: y
# - Certificate path: /Users/username/.azlin/certs/azlin-sp.pem
```

Or non-interactive:

```bash
azlin auth setup --profile prod \
  --tenant-id "87654321-4321-4321-4321-cba987654321" \
  --client-id "12345678-1234-1234-1234-123456789abc" \
  --subscription-id "abcdef12-3456-7890-abcd-ef1234567890" \
  --use-certificate \
  --certificate-path ~/.azlin/certs/azlin-sp.pem
```

**Step 4: Set Certificate Permissions**

Certificate files MUST have secure permissions (0600 or 0400):

```bash
# Set read/write for owner only
chmod 600 ~/.azlin/certs/azlin-sp.pem

# Or read-only for owner
chmod 400 ~/.azlin/certs/azlin-sp.pem

# Verify permissions
ls -la ~/.azlin/certs/azlin-sp.pem
# Should show: -rw-------  (600) or -r--------  (400)
```

**Security validation:**

azlin automatically validates certificate permissions during setup. If permissions are too permissive, you'll see:

```
✗ Certificate validation failed: Certificate has insecure permissions: 0644. Expected: 0600 or 0400
```

**Step 5: Test Authentication**

```bash
# Test certificate authentication
azlin auth test --profile prod
```

---

### Method 4: Managed Identity

**How it works:**
Uses the managed identity assigned to an Azure resource (VM, Container Instance, Function App). No credentials needed - authentication is automatic.

**When to use:**
- Azure-hosted workloads
- Azure VMs running azlin
- Azure Container Instances
- Azure Functions
- Any Azure service with managed identity support

**Benefits:**
- No credential management
- Automatic credential rotation
- Azure-native security
- Zero configuration on the workload

#### Step-by-Step Setup

**Step 1: Enable Managed Identity on Azure Resource**

For Azure VMs:

```bash
# Enable system-assigned managed identity
az vm identity assign \
  --name "my-vm" \
  --resource-group "my-rg"

# Output includes:
# {
#   "systemAssignedIdentity": "12345678-1234-1234-1234-123456789abc"
# }
```

For Azure Container Instances:

```bash
# Create container with managed identity
az container create \
  --name "azlin-worker" \
  --resource-group "my-rg" \
  --image "myregistry.azurecr.io/azlin-worker:latest" \
  --assign-identity
```

**Step 2: Grant Permissions to Managed Identity**

```bash
# Get managed identity principal ID
IDENTITY_ID=$(az vm identity show --name "my-vm" --resource-group "my-rg" --query principalId -o tsv)

# Grant Contributor role
az role assignment create \
  --assignee $IDENTITY_ID \
  --role Contributor \
  --scope /subscriptions/{SUBSCRIPTION-ID}
```

**Step 3: Configure azlin (Auto-Detection)**

When azlin runs on an Azure resource with managed identity, it automatically detects and uses it. No configuration needed!

```bash
# On the Azure VM/Container, just use azlin normally
azlin list
azlin new
```

For explicit configuration:

```bash
azlin auth setup --profile managed \
  --tenant-id "87654321-4321-4321-4321-cba987654321" \
  --subscription-id "abcdef12-3456-7890-abcd-ef1234567890" \
  --use-managed-identity
```

**Step 4: Test on Azure Resource**

```bash
# SSH into your Azure VM
ssh azureuser@your-vm-ip

# Test managed identity authentication
azlin auth test --profile managed
```

---

## Quick Start

### Interactive Setup

The easiest way to get started:

```bash
# Run interactive setup wizard
azlin auth setup

# Follow prompts to enter:
# - Profile name (e.g., "dev", "prod", "staging")
# - Tenant ID
# - Client ID
# - Subscription ID
# - Auth method (certificate or client secret)
```

### Manual Configuration

For non-interactive or scripted setup, edit `~/.azlin/config.toml` directly:

```toml
[auth.profiles.production]
client_id = "12345678-1234-1234-1234-123456789abc"
tenant_id = "87654321-4321-4321-4321-cba987654321"
subscription_id = "abcdef12-3456-7890-abcd-ef1234567890"
auth_method = "client_secret"

[auth.profiles.prod-cert]
client_id = "12345678-1234-1234-1234-123456789abc"
tenant_id = "87654321-4321-4321-4321-cba987654321"
subscription_id = "abcdef12-3456-7890-abcd-ef1234567890"
auth_method = "certificate"
certificate_path = "/Users/username/.azlin/certs/azlin-sp.pem"

[auth.profiles.dev]
client_id = "abcdefgh-5678-5678-5678-abcdefghijkl"
tenant_id = "87654321-4321-4321-4321-cba987654321"
subscription_id = "fedcba09-8765-4321-fedc-ba0987654321"
auth_method = "client_secret"
```

---

## Security Best Practices

### Critical Security Rules

1. **Never store secrets in config files** ⚠️
   - Use environment variables for client secrets
   - azlin config files should NEVER contain `client_secret` field
   - Review config before committing to version control

2. **Use environment variables for secrets**
   ```bash
   # Good practices
   export AZURE_CLIENT_SECRET="secret"
   export AZLIN_SP_CLIENT_SECRET="secret"

   # Bad practices (DO NOT DO THIS)
   # - Hardcoding in scripts
   # - Storing in config files
   # - Committing to Git
   ```

3. **Set certificate permissions to 0600 or 0400**
   ```bash
   # Correct permissions
   chmod 600 certificate.pem  # Read/write for owner only
   chmod 400 certificate.pem  # Read-only for owner only

   # Incorrect permissions (azlin will reject)
   chmod 644 certificate.pem  # Too permissive!
   chmod 755 certificate.pem  # Extremely insecure!
   ```

4. **Rotate secrets regularly**
   - Client secrets: Rotate every 90 days
   - Certificates: Set 1-year expiration, renew at 30 days
   - Document rotation procedures
   - Use Azure Key Vault for automatic rotation

5. **Use certificate-based auth when possible**
   - Higher security than client secrets
   - Better for production environments
   - Harder to compromise
   - Supports hardware security modules

6. **Grant minimum required permissions**
   - Start with Reader role, escalate as needed
   - Use resource group-level permissions when possible
   - Avoid subscription-wide Contributor unless necessary
   - Regular permission audits

### Security Checklist

Before deploying to production:

- [ ] No secrets in config files (`~/.azlin/config.toml`)
- [ ] Client secrets stored in environment variables only
- [ ] Certificate permissions are 0600 or 0400
- [ ] Service principal has minimum required permissions
- [ ] Secret rotation schedule documented
- [ ] Certificates expire in > 30 days
- [ ] Config file permissions are 0600
- [ ] No credentials in version control
- [ ] Azure Key Vault configured (for production)
- [ ] Audit logging enabled

---

## Configuration Examples

### Example 1: Dev Environment (Client Secret)

**Scenario:** Local development with client secret authentication

```bash
# Setup profile
azlin auth setup --profile dev \
  --tenant-id "87654321-4321-4321-4321-cba987654321" \
  --client-id "12345678-1234-1234-1234-123456789abc" \
  --subscription-id "dev-sub-id"

# Set secret
export AZURE_CLIENT_SECRET="dev-secret-here"

# Use profile
azlin --auth-profile dev list
azlin --auth-profile dev new --name dev-vm
```

**Config file** (`~/.azlin/config.toml`):

```toml
[auth.profiles.dev]
client_id = "12345678-1234-1234-1234-123456789abc"
tenant_id = "87654321-4321-4321-4321-cba987654321"
subscription_id = "dev-sub-id"
auth_method = "client_secret"
```

---

### Example 2: Production (Certificate-Based)

**Scenario:** Production environment with certificate authentication and Key Vault

```bash
# Generate certificate in Key Vault
az keyvault certificate create \
  --vault-name "prod-keyvault" \
  --name "azlin-prod-cert" \
  --policy "$(az keyvault certificate get-default-policy)"

# Download certificate
az keyvault secret download \
  --vault-name "prod-keyvault" \
  --name "azlin-prod-cert" \
  --file ~/.azlin/certs/prod-cert.pem

# Set permissions
chmod 400 ~/.azlin/certs/prod-cert.pem

# Setup profile
azlin auth setup --profile prod \
  --tenant-id "87654321-4321-4321-4321-cba987654321" \
  --client-id "prod-client-id" \
  --subscription-id "prod-sub-id" \
  --use-certificate \
  --certificate-path ~/.azlin/certs/prod-cert.pem

# Test
azlin auth test --profile prod

# Use profile
azlin --auth-profile prod list
```

**Config file** (`~/.azlin/config.toml`):

```toml
[auth.profiles.prod]
client_id = "prod-client-id"
tenant_id = "87654321-4321-4321-4321-cba987654321"
subscription_id = "prod-sub-id"
auth_method = "certificate"
certificate_path = "/Users/username/.azlin/certs/prod-cert.pem"
```

---

### Example 3: CI/CD Pipeline (GitHub Actions)

**Scenario:** Automated deployment in GitHub Actions

**GitHub Secrets Configuration:**

1. Go to repository **Settings** → **Secrets and variables** → **Actions**
2. Add secrets:
   - `AZURE_TENANT_ID`
   - `AZURE_CLIENT_ID`
   - `AZURE_CLIENT_SECRET`
   - `AZURE_SUBSCRIPTION_ID`

**Workflow file** (`.github/workflows/deploy.yml`):

```yaml
name: Azure Deployment with azlin

on:
  push:
    branches: [ main ]
  workflow_dispatch:

env:
  AZURE_TENANT_ID: ${{ secrets.AZURE_TENANT_ID }}
  AZURE_CLIENT_ID: ${{ secrets.AZURE_CLIENT_ID }}
  AZURE_CLIENT_SECRET: ${{ secrets.AZURE_CLIENT_SECRET }}

jobs:
  deploy:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout code
        uses: actions/checkout@v3

      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install azlin
        run: |
          pip install azlin

      - name: Configure azlin profile
        run: |
          azlin auth setup --profile ci \
            --tenant-id "$AZURE_TENANT_ID" \
            --client-id "$AZURE_CLIENT_ID" \
            --subscription-id "${{ secrets.AZURE_SUBSCRIPTION_ID }}"

      - name: Test authentication
        run: |
          azlin auth test --profile ci

      - name: List VMs
        run: |
          azlin --auth-profile ci list

      - name: Deploy VM
        run: |
          azlin --auth-profile ci new --name "ci-vm-${{ github.run_number }}"
```

---

### Example 4: Multiple Environments

**Scenario:** Dev, staging, and production profiles

```bash
# Setup development profile
azlin auth setup --profile dev \
  --tenant-id "$DEV_TENANT_ID" \
  --client-id "$DEV_CLIENT_ID" \
  --subscription-id "$DEV_SUBSCRIPTION_ID"

# Setup staging profile (certificate-based)
azlin auth setup --profile staging \
  --tenant-id "$STAGING_TENANT_ID" \
  --client-id "$STAGING_CLIENT_ID" \
  --subscription-id "$STAGING_SUBSCRIPTION_ID" \
  --use-certificate \
  --certificate-path ~/.azlin/certs/staging-cert.pem

# Setup production profile (certificate-based)
azlin auth setup --profile prod \
  --tenant-id "$PROD_TENANT_ID" \
  --client-id "$PROD_CLIENT_ID" \
  --subscription-id "$PROD_SUBSCRIPTION_ID" \
  --use-certificate \
  --certificate-path ~/.azlin/certs/prod-cert.pem

# Use profiles
export AZURE_CLIENT_SECRET="dev-secret"
azlin --auth-profile dev list

azlin --auth-profile staging list
azlin --auth-profile prod list
```

**Config file** (`~/.azlin/config.toml`):

```toml
[auth.profiles.dev]
client_id = "dev-client-id"
tenant_id = "dev-tenant-id"
subscription_id = "dev-subscription-id"
auth_method = "client_secret"

[auth.profiles.staging]
client_id = "staging-client-id"
tenant_id = "staging-tenant-id"
subscription_id = "staging-subscription-id"
auth_method = "certificate"
certificate_path = "/Users/username/.azlin/certs/staging-cert.pem"

[auth.profiles.prod]
client_id = "prod-client-id"
tenant_id = "prod-tenant-id"
subscription_id = "prod-subscription-id"
auth_method = "certificate"
certificate_path = "/Users/username/.azlin/certs/prod-cert.pem"
```

---

## Testing Authentication

### Basic Tests

```bash
# Test default profile
azlin auth test

# Test specific profile
azlin auth test --profile production

# Test with subscription validation
azlin auth test --profile prod --subscription-id "YOUR-SUB-ID"
```

### Expected Output

Successful authentication:

```
Testing authentication profile: production

Profile details:
  Client ID: 12345678-1234-1234-1234-123456789abc
  Tenant ID: 87654321-4321-4321-4321-cba987654321
  Subscription ID: abcdef12-3456-7890-abcd-ef1234567890
  Auth method: certificate
  Certificate: /Users/username/.azlin/certs/prod-cert.pem

Validating credentials...
✓ Credentials valid

Testing Azure authentication...
✓ Authentication successful!

  Authenticated as:
    Tenant: 87654321-4321-4321-4321-cba987654321
    Subscription: Production Subscription
    ID: abcdef12-3456-7890-abcd-ef1234567890
```

### Using Authentication Profiles

```bash
# Use profile with any azlin command
azlin --auth-profile prod list
azlin --auth-profile prod new --name test-vm
azlin --auth-profile prod status

# Set default profile via environment variable
export AZLIN_AUTH_PROFILE=prod
azlin list  # Uses prod profile automatically
```

---

## Profile Management

### List Profiles

```bash
azlin auth list
```

Output:

```
Authentication Profiles (3):

  dev
    Client ID: 12345678...
    Tenant ID: 87654321...
    Auth method: client_secret

  staging
    Client ID: abcdefgh...
    Tenant ID: 87654321...
    Auth method: certificate
    Certificate: /Users/username/.azlin/certs/staging-cert.pem

  prod
    Client ID: fedcba09...
    Tenant ID: 87654321...
    Auth method: certificate
    Certificate: /Users/username/.azlin/certs/prod-cert.pem

Use 'azlin auth show <profile>' for full details
```

### Show Profile Details

```bash
azlin auth show production
```

Output:

```
Profile: production

  Client ID: 12345678-1234-1234-1234-123456789abc
  Tenant ID: 87654321-4321-4321-4321-cba987654321
  Subscription ID: abcdef12-3456-7890-abcd-ef1234567890
  Auth method: certificate
  Certificate path: /Users/username/.azlin/certs/prod-cert.pem
  Certificate status: Valid ✓

  Config location: /Users/username/.azlin/config.toml
```

### Remove Profile

```bash
# Remove with confirmation prompt
azlin auth remove old-profile

# Remove without confirmation
azlin auth remove staging --yes
```

Output:

```
Profile 'staging' will be removed.
This will delete the profile configuration (not the Azure service principal).

Are you sure? [y/N]: y

✓ Profile 'staging' removed successfully!

Remaining profiles: dev, prod
```

---

## Troubleshooting

### Common Issues

#### 1. "Certificate permissions too permissive"

**Problem:** Certificate file has permissions 0644 or looser

**Error message:**
```
✗ Certificate validation failed: Certificate has insecure permissions: 0644. Expected: 0600 or 0400
```

**Solution:**
```bash
# Fix permissions
chmod 600 /path/to/certificate.pem

# Verify
ls -la /path/to/certificate.pem
# Should show: -rw-------  (600)

# Or set read-only
chmod 400 /path/to/certificate.pem
# Should show: -r--------  (400)

# Re-test
azlin auth test --profile prod
```

---

#### 2. "Client secret not found in environment"

**Problem:** AZURE_CLIENT_SECRET or AZLIN_SP_CLIENT_SECRET environment variable not set

**Error message:**
```
✗ Credential validation failed: Client secret not found in environment variables
```

**Solution:**
```bash
# Set client secret
export AZURE_CLIENT_SECRET="your-secret-here"

# Or use azlin-specific variable
export AZLIN_SP_CLIENT_SECRET="your-secret-here"

# Verify it's set
echo $AZURE_CLIENT_SECRET

# Make it permanent
echo 'export AZURE_CLIENT_SECRET="your-secret-here"' >> ~/.bashrc
source ~/.bashrc

# Re-test
azlin auth test --profile dev
```

---

#### 3. "Certificate expired or expiring soon"

**Problem:** Certificate expires within 30 days or has already expired

**Warning message:**
```
Warning: Certificate expires in 15 days on 2025-11-15
```

**Error message:**
```
✗ Certificate validation failed: Certificate has expired on 2025-10-15
```

**Solution:**
```bash
# Generate new certificate
openssl req -x509 -newkey rsa:4096 -keyout new-key.pem -out new-cert.pem -days 365 -nodes \
  -subj "/CN=azlin-service-principal"

# Combine
cat new-key.pem new-cert.pem > azlin-sp-new.pem
chmod 600 azlin-sp-new.pem
mv azlin-sp-new.pem ~/.azlin/certs/

# Update service principal
az ad sp credential reset \
  --id {CLIENT-ID} \
  --cert @~/.azlin/certs/azlin-sp-new.pem

# Update profile
azlin auth setup --profile prod \
  --tenant-id "$TENANT_ID" \
  --client-id "$CLIENT_ID" \
  --subscription-id "$SUBSCRIPTION_ID" \
  --use-certificate \
  --certificate-path ~/.azlin/certs/azlin-sp-new.pem

# Test
azlin auth test --profile prod
```

---

#### 4. "Invalid UUID format for tenant_id/client_id"

**Problem:** Tenant ID or Client ID is not in valid UUID format

**Error message:**
```
Error: Invalid tenant_id format: abc123
```

**Solution:**
```bash
# Get correct values from Azure Portal or CLI
# Tenant ID and Client ID must be in UUID format:
# 12345678-1234-1234-1234-123456789abc

# Get tenant ID
az account show --query tenantId -o tsv

# Get client ID for service principal
az ad sp list --display-name "azlin-automation" --query "[0].appId" -o tsv

# Use correct UUIDs in setup
azlin auth setup --profile prod \
  --tenant-id "$(az account show --query tenantId -o tsv)" \
  --client-id "$(az ad sp list --display-name 'azlin-automation' --query '[0].appId' -o tsv)" \
  --subscription-id "$(az account show --query id -o tsv)"
```

---

#### 5. "Authentication failed with service principal"

**Problem:** Incorrect credentials or insufficient permissions

**Error message:**
```
✗ Authentication failed
Error: AADSTS7000215: Invalid client secret provided
```

**Solution:**

Check credentials are correct:

```bash
# Verify tenant ID
az account show --query tenantId -o tsv

# Verify client ID
az ad sp show --id {CLIENT-ID} --query appId -o tsv

# Verify client secret (create new if unsure)
az ad sp credential reset --id {CLIENT-ID}

# Update environment variable with new secret
export AZURE_CLIENT_SECRET="new-secret-value"

# Re-test
azlin auth test --profile prod
```

Check permissions:

```bash
# List role assignments for service principal
az role assignment list --assignee {CLIENT-ID} --output table

# Grant required permissions if missing
az role assignment create \
  --assignee {CLIENT-ID} \
  --role Contributor \
  --scope /subscriptions/{SUBSCRIPTION-ID}

# Re-test
azlin auth test --profile prod
```

---

#### 6. "Profile not found"

**Problem:** Specified profile doesn't exist in configuration

**Error message:**
```
Error: Profile 'production' not found.

Available profiles: dev, staging
```

**Solution:**
```bash
# List available profiles
azlin auth list

# Create missing profile
azlin auth setup --profile production

# Or check for typo in profile name
azlin auth show prod  # Instead of 'production'
```

---

#### 7. "Azure CLI not found"

**Problem:** Azure CLI (`az` command) is not installed

**Error message:**
```
✗ Azure CLI not found
Please install Azure CLI: https://docs.microsoft.com/en-us/cli/azure/install-azure-cli
```

**Solution:**

macOS:
```bash
brew install azure-cli
```

Linux (Debian/Ubuntu):
```bash
curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash
```

Linux (RPM-based):
```bash
sudo rpm --import https://packages.microsoft.com/keys/microsoft.asc
sudo dnf install azure-cli
```

Windows:
```powershell
# Using winget
winget install Microsoft.AzureCLI

# Or download installer from:
# https://aka.ms/installazurecliwindows
```

Verify installation:
```bash
az --version
```

---

### Debug Mode

Enable verbose logging for detailed troubleshooting:

```bash
# Enable verbose output
azlin --verbose auth test --profile prod

# Check azlin logs
tail -f ~/.azlin/logs/azlin.log

# Test with Azure CLI debug mode
export AZURE_CLI_LOGGING_ENABLED=1
azlin auth test --profile prod
```

---

## Migration from Azure CLI

If you're currently using Azure CLI authentication and want to add service principal support:

### No Changes Required

Azure CLI authentication remains the default. Your existing workflows continue to work:

```bash
# Still works - uses Azure CLI by default
azlin list
azlin new
azlin status
```

### Opt-In to Service Principals

Service principals are completely opt-in. Only use them when you specify a profile:

```bash
# Uses Azure CLI (default)
azlin list

# Uses service principal (explicit)
azlin --auth-profile prod list
```

### Gradual Migration

1. **Continue using Azure CLI for development**
   ```bash
   az login
   azlin new  # Uses Azure CLI
   ```

2. **Add service principal for CI/CD**
   ```bash
   azlin auth setup --profile ci
   # Use in GitHub Actions
   ```

3. **Optionally migrate production to service principals**
   ```bash
   azlin auth setup --profile prod --use-certificate
   ```

### Fallback Behavior

azlin automatically falls back to Azure CLI if:
- No profile is specified
- Profile authentication fails
- Service principal credentials are invalid

This ensures seamless operation during migration.

---

## Creating Service Principal

### Using Azure CLI (Recommended)

#### Option 1: Create with Contributor Role

```bash
# Create service principal with Contributor role on subscription
az ad sp create-for-rbac \
  --name "azlin-automation" \
  --role Contributor \
  --scopes /subscriptions/{SUBSCRIPTION-ID}

# Output:
# {
#   "appId": "12345678-1234-1234-1234-123456789abc",      # CLIENT_ID
#   "displayName": "azlin-automation",
#   "password": "your-secret-value-here",                 # CLIENT_SECRET
#   "tenant": "87654321-4321-4321-4321-cba987654321"     # TENANT_ID
# }
```

#### Option 2: Create with Resource Group Scope

```bash
# Create with access only to specific resource group
az ad sp create-for-rbac \
  --name "azlin-dev" \
  --role Contributor \
  --scopes /subscriptions/{SUBSCRIPTION-ID}/resourceGroups/{RESOURCE-GROUP}
```

#### Option 3: Create with Certificate

```bash
# Generate certificate first
openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365 -nodes \
  -subj "/CN=azlin-service-principal"
cat key.pem cert.pem > azlin-sp.pem
chmod 600 azlin-sp.pem

# Create service principal with certificate
az ad sp create-for-rbac \
  --name "azlin-automation-cert" \
  --role Contributor \
  --scopes /subscriptions/{SUBSCRIPTION-ID} \
  --cert @azlin-sp.pem
```

### Using Azure Portal

#### Step-by-Step Instructions

1. **Navigate to Azure Active Directory**
   - Go to [Azure Portal](https://portal.azure.com)
   - Search for "Azure Active Directory" or select it from left menu

2. **Create App Registration**
   - Click **"App registrations"** in left menu
   - Click **"New registration"**
   - Name: `azlin-automation`
   - Supported account types: **"Accounts in this organizational directory only"**
   - Redirect URI: Leave blank
   - Click **"Register"**

3. **Note Application Details**
   - On the Overview page, copy:
     - **Application (client) ID** → Use as `CLIENT_ID`
     - **Directory (tenant) ID** → Use as `TENANT_ID`

4. **Create Client Secret** (for password-based auth)
   - Click **"Certificates & secrets"** in left menu
   - Click **"New client secret"**
   - Description: `azlin-secret`
   - Expires: **12 months** (recommended)
   - Click **"Add"**
   - **Copy the secret value immediately** (shown only once!) → Use as `CLIENT_SECRET`

5. **Upload Certificate** (for certificate-based auth)
   - Click **"Certificates & secrets"** in left menu
   - Click **"Upload certificate"**
   - Select your `.pem` or `.cer` file
   - Click **"Add"**

6. **Grant Permissions**
   - Go to your **Subscription** (search for "Subscriptions")
   - Select your subscription
   - Click **"Access control (IAM)"** in left menu
   - Click **"Add" → "Add role assignment"**
   - Role: **Contributor**
   - Members: Search for `azlin-automation`
   - Click **"Review + assign"**

---

## Granting Permissions

Service principals need appropriate Azure permissions to manage resources.

### Required Permissions

| Operation | Minimum Role | Scope |
|-----------|--------------|-------|
| List VMs | Reader | Subscription or Resource Group |
| Create VMs | Contributor | Resource Group |
| Start/Stop VMs | Virtual Machine Contributor | Resource Group |
| Manage Storage | Storage Account Contributor | Resource Group |
| View Costs | Cost Management Reader | Subscription |

### Permission Scopes

#### Subscription-Level (Broad Access)

```bash
# Grant Contributor role to entire subscription
az role assignment create \
  --assignee {CLIENT-ID} \
  --role Contributor \
  --scope /subscriptions/{SUBSCRIPTION-ID}
```

**Use when:**
- Managing resources across multiple resource groups
- Creating new resource groups dynamically
- Full subscription management

#### Resource Group-Level (Recommended)

```bash
# Grant Contributor role to specific resource group
az role assignment create \
  --assignee {CLIENT-ID} \
  --role Contributor \
  --scope /subscriptions/{SUBSCRIPTION-ID}/resourceGroups/{RESOURCE-GROUP}
```

**Use when:**
- Limiting access to specific workloads
- Team-based resource isolation
- Following least-privilege principle

#### Multiple Resource Groups

```bash
# Grant access to multiple resource groups
for RG in azlin-dev azlin-staging azlin-prod; do
  az role assignment create \
    --assignee {CLIENT-ID} \
    --role Contributor \
    --scope /subscriptions/{SUBSCRIPTION-ID}/resourceGroups/$RG
done
```

### Role Types

#### Built-in Roles

```bash
# Reader - Read-only access
az role assignment create \
  --assignee {CLIENT-ID} \
  --role Reader \
  --scope /subscriptions/{SUBSCRIPTION-ID}

# Virtual Machine Contributor - VM management only
az role assignment create \
  --assignee {CLIENT-ID} \
  --role "Virtual Machine Contributor" \
  --scope /subscriptions/{SUBSCRIPTION-ID}/resourceGroups/{RESOURCE-GROUP}

# Contributor - Full management (no permission changes)
az role assignment create \
  --assignee {CLIENT-ID} \
  --role Contributor \
  --scope /subscriptions/{SUBSCRIPTION-ID}
```

### Key Vault Permissions (if using)

```bash
# Grant access to Key Vault secrets
az role assignment create \
  --assignee {CLIENT-ID} \
  --role "Key Vault Secrets User" \
  --scope /subscriptions/{SUBSCRIPTION-ID}/resourceGroups/{RESOURCE-GROUP}/providers/Microsoft.KeyVault/vaults/{KEYVAULT-NAME}
```

### Verify Permissions

```bash
# List role assignments for service principal
az role assignment list \
  --assignee {CLIENT-ID} \
  --output table

# Output:
# Principal                             Role          Scope
# ------------------------------------  ------------  ----------------------------------------------------------------
# 12345678-1234-1234-1234-123456789abc  Contributor   /subscriptions/abcdef12-3456-7890-abcd-ef1234567890/resourceGroups/azlin-rg
```

---

## Environment Variables Reference

### Complete Variable List

| Variable | Required | Auth Method | Description |
|----------|----------|-------------|-------------|
| `AZURE_TENANT_ID` | Yes (SP/MI) | Service Principal, Managed Identity | Azure Active Directory tenant ID (UUID format) |
| `AZURE_CLIENT_ID` | Yes (SP/MI) | Service Principal, Managed Identity | Application (client) ID (UUID format) |
| `AZURE_CLIENT_SECRET` | Yes (secret) | Service Principal (Secret) | Client secret value for password-based auth |
| `AZLIN_SP_CLIENT_SECRET` | Alternative | Service Principal (Secret) | Alternative to AZURE_CLIENT_SECRET (azlin-specific) |
| `AZURE_CLIENT_CERTIFICATE_PATH` | Yes (cert) | Service Principal (Certificate) | Absolute path to certificate file (.pem) |
| `AZLIN_AUTH_PROFILE` | Optional | All | Default authentication profile to use |
| `AZURE_SUBSCRIPTION_ID` | Optional | All | Default subscription ID (if not in profile) |

### Variable Priority

When multiple variables are set, azlin uses this priority:

1. Command-line flags (`--auth-profile`, `--subscription-id`)
2. `AZLIN_AUTH_PROFILE` environment variable
3. Profile configuration in `~/.azlin/config.toml`
4. Azure CLI default subscription

### Setting Variables

#### Temporary (Current Session)

```bash
# Set for current terminal session only
export AZURE_TENANT_ID="87654321-4321-4321-4321-cba987654321"
export AZURE_CLIENT_ID="12345678-1234-1234-1234-123456789abc"
export AZURE_CLIENT_SECRET="your-secret-here"
```

#### Permanent (User Profile)

Bash (`~/.bashrc` or `~/.bash_profile`):
```bash
# Add to ~/.bashrc
cat >> ~/.bashrc <<'EOF'
export AZURE_TENANT_ID="87654321-4321-4321-4321-cba987654321"
export AZURE_CLIENT_ID="12345678-1234-1234-1234-123456789abc"
export AZURE_CLIENT_SECRET="your-secret-here"
EOF

# Reload
source ~/.bashrc
```

Zsh (`~/.zshrc`):
```bash
# Add to ~/.zshrc
cat >> ~/.zshrc <<'EOF'
export AZURE_TENANT_ID="87654321-4321-4321-4321-cba987654321"
export AZURE_CLIENT_ID="12345678-1234-1234-1234-123456789abc"
export AZURE_CLIENT_SECRET="your-secret-here"
EOF

# Reload
source ~/.zshrc
```

#### CI/CD (GitHub Actions)

```yaml
env:
  AZURE_TENANT_ID: ${{ secrets.AZURE_TENANT_ID }}
  AZURE_CLIENT_ID: ${{ secrets.AZURE_CLIENT_ID }}
  AZURE_CLIENT_SECRET: ${{ secrets.AZURE_CLIENT_SECRET }}
```

#### CI/CD (Azure DevOps)

```yaml
variables:
  - group: azure-credentials  # Variable group with secrets

pool:
  vmImage: ubuntu-latest

steps:
  - script: |
      azlin auth setup --profile prod \
        --tenant-id "$(AZURE_TENANT_ID)" \
        --client-id "$(AZURE_CLIENT_ID)" \
        --subscription-id "$(AZURE_SUBSCRIPTION_ID)"
    env:
      AZURE_CLIENT_SECRET: $(AZURE_CLIENT_SECRET)
```

### Verification

```bash
# Check if variables are set
echo $AZURE_TENANT_ID
echo $AZURE_CLIENT_ID
echo $AZURE_CLIENT_SECRET  # Shows secret (be careful!)

# Check without revealing secret
[ -n "$AZURE_CLIENT_SECRET" ] && echo "Secret is set" || echo "Secret not set"

# Test authentication
azlin auth test --profile prod
```

---

## Next Steps

After completing setup:

1. **Review Security Best Practices**
   - Follow the security guidelines in this document
   - Review permission scoping recommendations
   - Enable certificate-based authentication for production

2. **Understand Architecture**
   - Review authentication chain and fallback behavior
   - Understand how profiles work with contexts
   - Learn about multi-tenant authentication

3. **Start Using azlin**
   - See the [Quick Start Guide](../index.md) for general usage
   - Try the examples in [Command Reference](../commands/index.md)
   - Explore [Authentication Methods](./index.md)

4. **Join Community**
   - GitHub Issues: https://github.com/rysweet/azlin/issues
   - Discussions: https://github.com/rysweet/azlin/discussions

---

## Support

### Getting Help

**Documentation:**
- [Quick Start Guide](../index.md) - General azlin usage
- [Authentication Methods](./index.md) - Overview of auth methods
- [API Documentation](../api/index.md) - API reference
- [Command Reference](../commands/index.md) - All commands

**Troubleshooting:**
- Review [Troubleshooting](#troubleshooting) section above
- Check logs with `--verbose` flag
- Enable Azure CLI debug mode
- Search [GitHub Issues](https://github.com/rysweet/azlin/issues)

**Community:**
- Report bugs: [GitHub Issues](https://github.com/rysweet/azlin/issues/new)
- Request features: [GitHub Discussions](https://github.com/rysweet/azlin/discussions)
- Ask questions: Open an issue with `question` label

### Common Commands Quick Reference

```bash
# Setup
azlin auth setup --profile prod
azlin auth test --profile prod

# List profiles
azlin auth list
azlin auth show prod

# Use profile
azlin --auth-profile prod list
azlin --auth-profile prod new --name test-vm

# Remove profile
azlin auth remove old-profile

# Debug
azlin --verbose auth test --profile prod
```

---

## Integration with Azure Tags Feature

**New in v2.1**: Service principal authentication now works seamlessly with Azure VM tags for session management and cross-resource-group discovery.

### How It Works Together

When you use `--auth-profile`, azlin:
1. Authenticates with the specified service principal
2. Sets Azure environment variables (AZURE_CLIENT_ID, etc.)
3. All Azure CLI commands inherit these credentials
4. TagManager operations automatically use the service principal
5. Your personal Azure CLI login remains unchanged

### Cross-Resource-Group Discovery with Service Principal

**Scenario**: Discover all azlin-managed VMs across your entire subscription using a service principal

```bash
# Setup service principal profile (one-time)
azlin auth setup --profile team-vms
export AZURE_CLIENT_SECRET="your-sp-secret"

# List ALL azlin VMs across ALL resource groups
azlin --auth-profile team-vms list

# Output shows VMs from multiple resource groups:
# SESSION NAME              VM NAME                             STATUS    IP              REGION     SIZE
# amplihack-dev             azlin-vm-1761056536                 Running   20.9.184.101    westus2    Standard_D2s_v3
# simserv                   azlin-vm-1760983759                 Running   4.246.117.21    westus2    Standard_D2s_v3
# atg                       azlin-vm-1760928027                 Running   4.155.31.150    eastus     Standard_D2s_v3
```

### Tag-Based Session Management with Service Principal

**Session names are stored in Azure VM tags**, which means:
- The service principal needs `Microsoft.Compute/virtualMachines/write` permission
- Session names are shared across all users of the service principal
- Perfect for team environments

```bash
# Set session name using service principal
azlin --auth-profile team-vms session azlin-vm-123 production

# This writes to Azure VM tags:
# - managed-by: azlin
# - azlin-session: production
# - azlin-created: 2025-10-24T...
# - azlin-owner: team-vms

# Anyone using the same service principal sees the session
azlin --auth-profile team-vms list
# Shows "production" in SESSION NAME column
```

### Multi-Subscription Management

Manage VMs across different subscriptions with different service principals:

```bash
# Development subscription
azlin --auth-profile dev-sub list
azlin --auth-profile dev-sub new --name dev-vm --session testing

# Production subscription
azlin --auth-profile prod-sub list
azlin --auth-profile prod-sub session prod-vm-1 api-server

# Your personal Azure work (different auth context)
az vm list --subscription my-personal-sub
```

### Team Collaboration Example

**Setup (Team Lead)**:
```bash
# Create service principal for team
az ad sp create-for-rbac --name "team-azlin-sp" --role Contributor

# Share credentials with team (secure channel)
# Store in team password manager or Azure Key Vault
```

**Usage (Team Members)**:
```bash
# Each team member configures same profile
azlin auth setup --profile team
export AZURE_CLIENT_SECRET="team-shared-secret"

# Everyone sees the same VMs and session names
azlin --auth-profile team list

# Session names are shared (stored in Azure tags)
azlin --auth-profile team session worker-1 alice-dev
azlin --auth-profile team session worker-2 bob-dev
```

### CI/CD Automation Example

**GitHub Actions with Azure Tags**:
```yaml
name: Manage Azure VMs

on:
  push:
    branches: [main]

jobs:
  vm-management:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Setup azlin
        run: pip install azlin

      - name: Configure service principal
        env:
          AZURE_CLIENT_SECRET: ${{ secrets.AZLIN_SP_SECRET }}
        run: |
          azlin auth setup --profile ci \
            --client-id ${{ secrets.AZLIN_CLIENT_ID }} \
            --tenant-id ${{ secrets.AZLIN_TENANT_ID }} \
            --subscription-id ${{ secrets.AZLIN_SUBSCRIPTION_ID }}

      - name: List all VMs (cross-RG discovery)
        env:
          AZURE_CLIENT_SECRET: ${{ secrets.AZLIN_SP_SECRET }}
        run: azlin --auth-profile ci list

      - name: Create test VM with session tag
        env:
          AZURE_CLIENT_SECRET: ${{ secrets.AZLIN_SP_SECRET }}
        run: |
          azlin --auth-profile ci new --name "ci-vm-${{ github.run_number }}" \
            --session "ci-test-${{ github.run_number }}"

      - name: Clean up
        env:
          AZURE_CLIENT_SECRET: ${{ secrets.AZLIN_SP_SECRET }}
        run: azlin --auth-profile ci kill "ci-test-${{ github.run_number }}"
```

### Required Service Principal Permissions

For full Azure tags functionality, your service principal needs:

```bash
az role assignment create \
  --assignee "YOUR_SP_CLIENT_ID" \
  --role "Virtual Machine Contributor" \
  --scope "/subscriptions/YOUR_SUBSCRIPTION_ID"
```

This role includes:
- `Microsoft.Compute/virtualMachines/read` - List VMs and read tags
- `Microsoft.Compute/virtualMachines/write` - Create VMs and write tags
- `Microsoft.Compute/virtualMachines/delete` - Delete VMs
- Plus network and resource group operations

### Benefits of Tags + Service Principal

✅ **Separate authentication contexts** - azlin uses SP, you use personal login
✅ **Cross-resource-group discovery** - Find all team VMs with one command
✅ **Shared session names** - Everyone on team sees same labels
✅ **Multi-machine sync** - Session names in Azure, not local config
✅ **Audit trail** - SP operations tracked separately in Azure logs
✅ **Team collaboration** - Multiple users share same VM pool
✅ **CI/CD automation** - Fully automated VM lifecycle management

### Troubleshooting

**Problem**: "Authentication failed" when using --auth-profile
```bash
# Verify profile exists
azlin auth list

# Test authentication
azlin auth test --profile your-profile

# Check environment variable is set
echo $AZURE_CLIENT_SECRET
```

**Problem**: "Failed to set session name in VM tags"
```bash
# Verify SP has write permissions
az role assignment list --assignee YOUR_SP_CLIENT_ID --output table

# Should show "Virtual Machine Contributor" or "Contributor" role
```

**Problem**: "No VMs found" with cross-RG list
```bash
# Verify VMs have managed-by=azlin tag
az vm show --name VM_NAME --resource-group RG --query tags

# Tag new VMs manually if needed
azlin --auth-profile team session old-vm my-session
```

---

**Document Version:** 2.0
**Last Updated:** 2025-10-24
**Feedback:** Open an issue at https://github.com/rysweet/azlin/issues
