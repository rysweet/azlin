# Getting Started with Azlin Mobile PWA

**Learn how to install, configure, and run Azlin Mobile PWA on your iPhone.**

This guide walks you through setting up the Azlin Mobile PWA from scratch, including Azure authentication and first-time VM access.

## Prerequisites

Before you begin, ensure you have:

- **iOS Device**: iPhone or iPad running iOS 16+ or iPadOS 16+
- **Azure Subscription**: Active Azure subscription with VM creation permissions
- **Azure CLI**: Installed locally for initial setup (`az version 2.45+`)
- **Node.js**: Version 18 or higher (for local development)
- **Git**: For cloning the repository

## Installation

### Step 1: Clone the Repository

```bash
git clone https://github.com/rysweet/azlin.git
cd azlin/pwa
```

### Step 2: Install Dependencies

```bash
npm install
```

This installs all required packages including:
- React 18
- Azure Identity SDK
- Azure REST API clients
- Service worker tools

### Step 3: Configure Environment

**Zero-Config Experience**: If ye've already configured azlin with Azure CLI, the PWA auto-generates yer `.env` file from existing config!

#### Automatic Configuration (Recommended)

If ye've run `azlin` before and logged into Azure:

```bash
# Just start the PWA - config happens automatically
npm start

# Output shows where each config value came from:
# ✓ Tenant ID: from Azure CLI (az account show)
# ✓ Subscription ID: from Azure CLI
# ✓ Bastion Name: from azlin config (~/.azlin/config.json)
# ✓ Bastion RG: from azlin config
# ! Client ID: Manual setup required (see below)
```

**What gets auto-configured:**
- Tenant ID (from `az account show`)
- Subscription ID (from `az account show`)
- Bastion name and resource group (from `~/.azlin/config.json`)

**What needs manual setup:**
- Client ID (requires Azure AD app registration - see Step 4)

**Important**: Auto-generation NEVER overwrites an existing `.env` file. Yer manual customizations be safe!

#### Manual Configuration (If Needed)

If automatic config fails or ye want full control:

```bash
cp .env.example .env
```

Edit `.env` with yer Azure details:

```bash
# Azure AD Configuration
REACT_APP_AZURE_CLIENT_ID=your-app-registration-client-id
REACT_APP_AZURE_TENANT_ID=your-tenant-id

# Azure Subscription
REACT_APP_AZURE_SUBSCRIPTION_ID=your-subscription-id

# Azure Bastion (REQUIRED for private IP VMs)
REACT_APP_AZURE_BASTION_NAME=your-bastion-name
REACT_APP_AZURE_BASTION_RG=your-bastion-resource-group

# Feature Flags
REACT_APP_ENABLE_COST_TRACKING=true
REACT_APP_ENABLE_NOTIFICATIONS=true
```

### Step 4: Register Azure AD Application

The PWA requires an Azure AD app registration for authentication with specific permissions.

```bash
# Create app registration
az ad app create \
  --display-name "Azlin Mobile PWA" \
  --public-client-redirect-uris "https://localhost:3000/auth/callback" \
  --enable-device-flow true

# Get the client ID (save this for .env)
az ad app list --display-name "Azlin Mobile PWA" --query "[0].appId" -o tsv

# Grant API permissions (requires admin consent)
az ad app permission add \
  --id <client-id> \
  --api 00000002-0000-0000-c000-000000000000 \
  --api-permissions 311a71cc-e848-46a1-bdf8-97ff7156d8e6=Scope
```

**Required Azure RBAC Roles**:

The Azure AD user or service principal needs these roles:

- **Virtual Machine Contributor**: To manage VMs (start, stop, delete)
  ```bash
  az role assignment create \
    --assignee <user-or-sp-id> \
    --role "Virtual Machine Contributor" \
    --scope /subscriptions/<subscription-id>
  ```

- **Run Command Contributor**: To execute Azure Run Command for tmux snapshots
  ```bash
  az role assignment create \
    --assignee <user-or-sp-id> \
    --role "Run Command Contributor" \
    --scope /subscriptions/<subscription-id>
  ```

- **Cost Management Reader**: To access cost data
  ```bash
  az role assignment create \
    --assignee <user-or-sp-id> \
    --role "Cost Management Reader" \
    --scope /subscriptions/<subscription-id>
  ```

**Minimum Permissions Principle**:
- Avoid using Owner or Contributor roles
- Scope permissions to specific resource groups if possible
- Use separate service principals for production vs development

### Step 5: Run Development Server

```bash
npm start
```

The app opens at `http://localhost:3000`.

## Authentication Setup

### Device Code Flow

Azlin Mobile PWA uses Azure AD device code flow, optimized for mobile:

1. **Initiate Login**: Tap "Sign in with Azure" on the home screen
2. **Device Code Display**: A code appears (e.g., `A1B2C3D4`)
3. **Browser Authentication**: App opens `https://microsoft.com/devicelogin`
4. **Enter Code**: Enter the device code in the browser
5. **Consent**: Grant permissions for VM management
6. **Return to App**: App automatically detects successful authentication

**Example Device Code Screen:**
```
To sign in, visit:
https://microsoft.com/devicelogin

Enter code: A1B2C3D4

This code expires in 15 minutes.
```

### Token Management

After successful authentication:

- **Access Token**: Valid for 1 hour, used for API calls
- **Refresh Token**: Valid for 90 days, stored securely in iOS Keychain
- **Auto-Refresh**: App refreshes tokens automatically before expiry

Check authentication status:

```javascript
// In browser console (development only)
window.azlin.auth.getStatus()
// Output: { authenticated: true, expiresIn: 3456, user: "user@domain.com" }
```

## First VM Connection

### Create Your First VM

```bash
# From the PWA UI:
1. Tap "+" button (bottom right)
2. Select "Create New VM"
3. Fill in details:
   - Name: dev-vm-01
   - Size: Standard_D2s_v3
   - Region: eastus
   - Image: Ubuntu 22.04
4. Tap "Create" (takes 3-5 minutes)
```

### Connect via Bastion

**REQUIRED for VMs with private IPs only** (no public IP address):

```bash
# In PWA, tap VM name
1. Select "Connect via Bastion"
2. Wait for snapshot (5-10 seconds)
3. View tmux session output
4. Send commands in command box
```

**Example Command:**
```bash
# Type in command box:
ls -la /home/azureuser

# Tap "Send" - waits for next snapshot to show output
```

### View Tmux Sessions

```bash
# PWA automatically detects tmux sessions:
1. Navigate to VM detail page
2. Tap "Sessions" tab
3. See list of active tmux sessions
4. Tap session name to view snapshot
```

**Screenshot Description**: The Sessions tab shows a list with:
- Session name (e.g., "dev-session")
- Last activity time ("2 minutes ago")
- Window count ("3 windows")
- Snapshot preview (last 10 lines)

## Installing on iPhone

### Add to Home Screen

1. **Open in Safari**: Navigate to your deployed PWA URL
2. **Share Menu**: Tap the share icon (box with arrow)
3. **Add to Home Screen**: Scroll down and select
4. **Customize**: Edit name and icon if desired
5. **Add**: Tap "Add" in top-right

**Icon Behavior:**
- App icon appears on home screen
- Opens in full-screen mode (no Safari UI)
- Supports background refresh for notifications

### PWA Features on iOS

Once installed, the PWA provides:

- **Offline Access**: View cached VM data without connection
- **Push Notifications**: VM status alerts (requires permission)
- **Background Sync**: Updates when app is backgrounded
- **Native Feel**: No browser chrome, full-screen experience

## Troubleshooting

### Authentication Fails

**Problem**: "Failed to authenticate with Azure"

**Solution**:
```bash
# Verify app registration
az ad app show --id <client-id>

# Check redirect URIs include your domain
az ad app show --id <client-id> --query "publicClient.redirectUris"

# Ensure device flow is enabled
az ad app show --id <client-id> --query "publicClient.allowDeviceCodeFlow"
# Should output: true
```

### Cannot Connect to VM

**Problem**: "Connection timeout" when connecting to VM

**Solution**:
1. Verify VM is running: `az vm show -g <rg> -n <vm-name> --query "powerState"`
2. Check network security group allows Azure Run Command
3. **For private IP VMs**: Verify Azure Bastion is deployed (REQUIRED, not optional)
4. Test with Azure CLI: `az vm run-command invoke ...`

**Important**: VMs with only private IPs CANNOT be accessed without Azure Bastion. This is not optional - Bastion provides the only secure connection method for private VMs.

### Tmux Not Detected

**Problem**: "No tmux sessions found"

**Solution**:
```bash
# SSH to VM and install tmux
sudo apt-get update && sudo apt-get install -y tmux

# Start a session
tmux new -s test-session

# Verify from PWA (refresh VM page)
```

### Automatic Configuration Not Working

**Problem**: PWA falls back to manual configuration

**Possible causes and solutions:**

1. **Azure CLI not configured**
   ```bash
   # Check if Azure CLI is logged in
   az account show

   # If not logged in:
   az login
   ```

2. **Azlin config file missing**
   ```bash
   # Check if azlin config exists
   cat ~/.azlin/config.json

   # If missing, run azlin at least once:
   azlin vm list
   ```

3. **Missing Bastion configuration**
   ```bash
   # Azlin config exists but no Bastion set up
   # Run azlin to configure Bastion:
   azlin bastion setup
   ```

**Fallback behavior**: If auto-config fails, the PWA tells ye exactly what's missin' and how to fix it. Ye can always create `.env` manually if needed.

### PWA Won't Install

**Problem**: "Add to Home Screen" not appearing

**Requirements**:
- Must use Safari browser (not Chrome or others)
- Must be HTTPS (or localhost for dev)
- Must have valid manifest.json
- Must have registered service worker

**Verify in Safari Developer Console**:
```javascript
navigator.serviceWorker.getRegistrations().then(regs => console.log(regs))
// Should show at least one registration
```

## Next Steps

- **[Features Guide](./features.md)**: Learn about all available features
- **[Architecture](./architecture.md)**: Understand how the PWA works
- **[Deployment](./deployment.md)**: Deploy to Azure Static Web Apps

## Support

- **Issues**: Report bugs at [GitHub Issues](https://github.com/rysweet/azlin/issues)
- **Questions**: Ask in [GitHub Discussions](https://github.com/rysweet/azlin/discussions)
