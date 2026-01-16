# Deploying Azlin Mobile PWA

**Deploy the Azlin Mobile PWA to Azure Static Web Apps for production use.**

This guide covers deploying your PWA to Azure, configuring custom domains, and setting up CI/CD.

## Contents

- [Prerequisites](#prerequisites)
- [Azure Static Web Apps Setup](#azure-static-web-apps-setup)
- [GitHub Actions CI/CD](#github-actions-cicd)
- [Custom Domain Configuration](#custom-domain-configuration)
- [Environment Variables](#environment-variables)
- [SSL Certificates](#ssl-certificates)
- [Monitoring and Logs](#monitoring-and-logs)

## Prerequisites

Before deploying, ensure you have:

- **Azure Account**: Active Azure subscription
- **GitHub Account**: For CI/CD integration
- **Azure CLI**: Version 2.45 or higher
- **Node.js**: Version 18 or higher
- **Repository Access**: Push access to your GitHub repo

**Verify Prerequisites**:
```bash
# Check Azure CLI
az --version
# Output: azure-cli 2.45.0

# Check Node.js
node --version
# Output: v18.17.0

# Login to Azure
az login
```

## Azure Static Web Apps Setup

### Step 1: Create Resource Group

```bash
# Create resource group for PWA resources
az group create \
  --name azlin-pwa-rg \
  --location eastus2

# Verify creation
az group show --name azlin-pwa-rg --query "properties.provisioningState"
# Output: "Succeeded"
```

### Step 2: Create Static Web App

```bash
# Create static web app (free tier)
az staticwebapp create \
  --name azlin-mobile-pwa \
  --resource-group azlin-pwa-rg \
  --location eastus2 \
  --source https://github.com/yourusername/azlin \
  --branch main \
  --app-location "/pwa" \
  --output-location "build" \
  --login-with-github

# Get deployment token (needed for GitHub Actions)
az staticwebapp secrets list \
  --name azlin-mobile-pwa \
  --resource-group azlin-pwa-rg \
  --query "properties.apiKey" -o tsv
```

**What This Creates**:
- Static Web App resource in Azure
- Default `*.azurestaticapps.net` domain
- GitHub Actions workflow (auto-generated)
- Deployment token for CI/CD

### Step 3: Configure Build Settings

Create `staticwebapp.config.json` in `/pwa` directory:

```json
{
  "navigationFallback": {
    "rewrite": "/index.html",
    "exclude": ["/images/*.{png,jpg,gif}", "/css/*"]
  },
  "routes": [
    {
      "route": "/api/*",
      "allowedRoles": ["authenticated"]
    }
  ],
  "responseOverrides": {
    "401": {
      "redirect": "/auth/login",
      "statusCode": 302
    },
    "404": {
      "rewrite": "/index.html",
      "statusCode": 200
    }
  },
  "globalHeaders": {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": "default-src 'self' https://*.azure.com https://*.microsoft.com"
  },
  "mimeTypes": {
    ".json": "application/json",
    ".webmanifest": "application/manifest+json"
  }
}
```

## GitHub Actions CI/CD

### Step 1: Add Deployment Token

Add the deployment token as a GitHub secret:

```bash
# In GitHub repo:
1. Go to Settings → Secrets and variables → Actions
2. Click "New repository secret"
3. Name: AZURE_STATIC_WEB_APPS_API_TOKEN
4. Value: <token from az staticwebapp secrets list>
5. Click "Add secret"
```

### Step 2: Create Workflow File

Create `.github/workflows/azure-static-web-apps.yml`:

**Note**: Test steps are omitted until tests are implemented. The workflow focuses on building and deploying the PWA.

```yaml
name: Deploy Azlin Mobile PWA

on:
  push:
    branches:
      - main
    paths:
      - 'pwa/**'
  pull_request:
    types: [opened, synchronize, reopened, closed]
    branches:
      - main
    paths:
      - 'pwa/**'

jobs:
  build_and_deploy:
    if: github.event_name == 'push' || (github.event_name == 'pull_request' && github.event.action != 'closed')
    runs-on: ubuntu-latest
    name: Build and Deploy
    steps:
      - uses: actions/checkout@v3
        with:
          submodules: true

      - name: Setup Node.js
        uses: actions/setup-node@v3
        with:
          node-version: '18'
          cache: 'npm'
          cache-dependency-path: pwa/package-lock.json

      - name: Install dependencies
        run: |
          cd pwa
          npm ci

      - name: Build
        run: |
          cd pwa
          npm run build
        env:
          REACT_APP_AZURE_CLIENT_ID: ${{ secrets.AZURE_CLIENT_ID }}
          REACT_APP_AZURE_TENANT_ID: ${{ secrets.AZURE_TENANT_ID }}
          REACT_APP_AZURE_SUBSCRIPTION_ID: ${{ secrets.AZURE_SUBSCRIPTION_ID }}

      - name: Deploy to Azure Static Web Apps
        uses: Azure/static-web-apps-deploy@v1
        with:
          azure_static_web_apps_api_token: ${{ secrets.AZURE_STATIC_WEB_APPS_API_TOKEN }}
          repo_token: ${{ secrets.GITHUB_TOKEN }}
          action: "upload"
          app_location: "/pwa"
          api_location: ""
          output_location: "build"

  close_pull_request:
    if: github.event_name == 'pull_request' && github.event.action == 'closed'
    runs-on: ubuntu-latest
    name: Close Pull Request
    steps:
      - name: Close Pull Request
        uses: Azure/static-web-apps-deploy@v1
        with:
          azure_static_web_apps_api_token: ${{ secrets.AZURE_STATIC_WEB_APPS_API_TOKEN }}
          action: "close"
```

### Step 3: Add Environment Secrets

Add Azure credentials as GitHub secrets:

```bash
# In GitHub repo Settings → Secrets:
AZURE_CLIENT_ID: <your-app-registration-client-id>
AZURE_TENANT_ID: <your-tenant-id>
AZURE_SUBSCRIPTION_ID: <your-subscription-id>
```

### Step 4: Trigger Deployment

```bash
# Commit and push
git add .github/workflows/azure-static-web-apps.yml
git add pwa/staticwebapp.config.json
git commit -m "Add Azure Static Web Apps deployment"
git push origin main

# Monitor deployment
gh run watch
# Or view in GitHub UI: Actions tab
```

**Deployment Progress**:
1. GitHub Actions triggered on push
2. Node.js setup and dependencies installed (2-3 minutes)
3. Tests run (1-2 minutes)
4. Build created (1-2 minutes)
5. Deployed to Azure Static Web Apps (1-2 minutes)
6. **Total time**: 5-10 minutes

## Custom Domain Configuration

### Step 1: Add Custom Domain

```bash
# Add custom domain
az staticwebapp hostname set \
  --name azlin-mobile-pwa \
  --resource-group azlin-pwa-rg \
  --hostname pwa.azlin.io

# Get validation token
az staticwebapp hostname show \
  --name azlin-mobile-pwa \
  --resource-group azlin-pwa-rg \
  --hostname pwa.azlin.io
```

### Step 2: Configure DNS

Add DNS records at your domain registrar:

**For CNAME (recommended)**:
```
Type: CNAME
Name: pwa
Value: <your-app>.azurestaticapps.net
TTL: 3600
```

**For APEX domain (A record)**:
```
Type: A
Name: @
Value: <IP from Azure portal>
TTL: 3600
```

**Validation TXT Record**:
```
Type: TXT
Name: _dnsauth.pwa
Value: <validation-token from Azure>
TTL: 3600
```

### Step 3: Verify Domain

```bash
# Wait for DNS propagation (5-30 minutes)
nslookup pwa.azlin.io

# Verify in Azure
az staticwebapp hostname show \
  --name azlin-mobile-pwa \
  --resource-group azlin-pwa-rg \
  --hostname pwa.azlin.io \
  --query "properties.status"
# Output: "Ready"
```

### Step 4: Enable SSL

SSL is automatically provisioned by Azure Static Web Apps:

```bash
# Check SSL certificate status
az staticwebapp hostname show \
  --name azlin-mobile-pwa \
  --resource-group azlin-pwa-rg \
  --hostname pwa.azlin.io \
  --query "properties.sslState"
# Output: "Ready"
```

**SSL Certificate Details**:
- Provider: DigiCert (via Azure)
- Type: Domain Validation (DV)
- Auto-renewal: Yes (before expiry)
- Forced HTTPS: Enabled by default

## Environment Variables

### Production Environment

Create `.env.production` in `/pwa`:

```bash
# Azure AD Configuration
REACT_APP_AZURE_CLIENT_ID=your-production-client-id
REACT_APP_AZURE_TENANT_ID=your-tenant-id

# Azure Subscription
REACT_APP_AZURE_SUBSCRIPTION_ID=your-subscription-id

# Azure Bastion
REACT_APP_AZURE_BASTION_NAME=prod-bastion
REACT_APP_AZURE_BASTION_RG=prod-bastion-rg

# Feature Flags
REACT_APP_ENABLE_COST_TRACKING=true
REACT_APP_ENABLE_NOTIFICATIONS=true
REACT_APP_ENABLE_ANALYTICS=true

# API Configuration
REACT_APP_API_TIMEOUT=30000
REACT_APP_MAX_RETRIES=3

# PWA Configuration
REACT_APP_SERVICE_WORKER_UPDATE_INTERVAL=3600000
```

### Environment-Specific Builds

```bash
# Build for production
npm run build
# Uses .env.production

# Build for staging
REACT_APP_ENV=staging npm run build
# Uses .env.staging

# Build for development
npm run build:dev
# Uses .env.development
```

## SSL Certificates

### Certificate Management

Azure Static Web Apps handles SSL automatically, but you can verify:

```bash
# Check certificate details
openssl s_client -connect pwa.azlin.io:443 -servername pwa.azlin.io < /dev/null 2>/dev/null | openssl x509 -noout -text

# Check expiry date
echo | openssl s_client -servername pwa.azlin.io -connect pwa.azlin.io:443 2>/dev/null | openssl x509 -noout -dates
# Output:
# notBefore=Jan 15 00:00:00 2024 GMT
# notAfter=Apr 15 23:59:59 2024 GMT
```

### Renewal Process

- **Automatic Renewal**: Azure renews 30 days before expiry
- **Notification**: Email sent to admin 7 days before expiry
- **Monitoring**: Check certificate status in Azure Portal

### HTTPS Enforcement

Update `staticwebapp.config.json` to enforce HTTPS:

```json
{
  "routes": [
    {
      "route": "/*",
      "headers": {
        "Strict-Transport-Security": "max-age=31536000; includeSubDomains"
      }
    }
  ]
}
```

## Monitoring and Logs

### Application Insights

Enable Application Insights for PWA monitoring:

```bash
# Create Application Insights
az monitor app-insights component create \
  --app azlin-pwa-insights \
  --location eastus2 \
  --resource-group azlin-pwa-rg

# Get instrumentation key
az monitor app-insights component show \
  --app azlin-pwa-insights \
  --resource-group azlin-pwa-rg \
  --query "instrumentationKey" -o tsv
```

Add to `.env.production`:
```bash
REACT_APP_APPINSIGHTS_KEY=your-instrumentation-key
```

Update `src/index.js`:
```javascript
import { ApplicationInsights } from '@microsoft/applicationinsights-web';

const appInsights = new ApplicationInsights({
  config: {
    instrumentationKey: process.env.REACT_APP_APPINSIGHTS_KEY,
    enableAutoRouteTracking: true
  }
});
appInsights.loadAppInsights();
```

### View Logs

**Deployment Logs**:
```bash
# View GitHub Actions logs
gh run list
gh run view <run-id>

# View Azure logs
az staticwebapp logs show \
  --name azlin-mobile-pwa \
  --resource-group azlin-pwa-rg
```

**Application Logs** (in Application Insights):
```bash
# Query logs
az monitor app-insights query \
  --app azlin-pwa-insights \
  --resource-group azlin-pwa-rg \
  --analytics-query "traces | where timestamp > ago(1h) | order by timestamp desc"
```

### Metrics Dashboard

Key metrics to monitor:

- **Requests**: Total requests per day
- **Response Time**: P50, P95, P99 latency
- **Error Rate**: 4xx and 5xx responses
- **User Sessions**: Active users and sessions
- **PWA Install Rate**: Add-to-home-screen conversions

**Create Dashboard**:
```bash
# In Azure Portal:
1. Navigate to Application Insights → Workbooks
2. Select "Empty" template
3. Add queries:
   - requests | summarize count() by bin(timestamp, 1h)
   - requests | summarize avg(duration) by bin(timestamp, 1h)
   - exceptions | summarize count() by problemId
4. Save as "Azlin PWA Dashboard"
```

## Rollback Procedures

### Rollback to Previous Version

```bash
# List deployments
az staticwebapp show \
  --name azlin-mobile-pwa \
  --resource-group azlin-pwa-rg \
  --query "properties.{currentBuild:repositoryUrl,branch:branch}"

# Rollback via GitHub
git revert <commit-hash>
git push origin main

# Or deploy specific commit
git checkout <previous-commit>
git push origin main --force  # Use with caution
```

### Emergency Rollback

If production is broken:

```bash
# Deploy previous build manually
cd pwa
git checkout <previous-working-commit>
npm ci
npm run build

# Deploy with Azure CLI
az staticwebapp users update \
  --name azlin-mobile-pwa \
  --resource-group azlin-pwa-rg \
  --deployment-source ./build
```

## Performance Optimization

### CDN Configuration

Azure Static Web Apps includes global CDN by default. Verify:

```bash
# Check CDN headers
curl -I https://pwa.azlin.io
# Look for: X-Cache: HIT, X-Azure-Ref
```

### Compression

Enable Brotli compression in `staticwebapp.config.json`:

```json
{
  "globalHeaders": {
    "Content-Encoding": "br"
  }
}
```

### Caching Headers

```json
{
  "routes": [
    {
      "route": "/static/*",
      "headers": {
        "Cache-Control": "public, max-age=31536000, immutable"
      }
    },
    {
      "route": "/index.html",
      "headers": {
        "Cache-Control": "no-cache"
      }
    }
  ]
}
```

## Troubleshooting

### Deployment Fails

**Problem**: GitHub Actions deployment fails

**Solution**:
```bash
# Check logs
gh run view --log

# Common issues:
# 1. Invalid deployment token
az staticwebapp secrets list --name azlin-mobile-pwa --resource-group azlin-pwa-rg

# 2. Build errors
cd pwa && npm run build  # Test locally

# 3. Missing environment variables
# Verify in GitHub Settings → Secrets
```

### Domain Not Resolving

**Problem**: Custom domain shows "Not found"

**Solution**:
```bash
# Check DNS propagation
nslookup pwa.azlin.io
dig pwa.azlin.io

# Verify CNAME record
dig pwa.azlin.io CNAME

# Check Azure configuration
az staticwebapp hostname show \
  --name azlin-mobile-pwa \
  --resource-group azlin-pwa-rg \
  --hostname pwa.azlin.io
```

### SSL Certificate Issues

**Problem**: SSL certificate not provisioned

**Solution**:
```bash
# Check certificate status
az staticwebapp hostname show \
  --name azlin-mobile-pwa \
  --resource-group azlin-pwa-rg \
  --hostname pwa.azlin.io \
  --query "properties.sslState"

# If "Pending", wait up to 24 hours
# If "Failed", check DNS validation record
```

## Cost Optimization

### Free Tier Limits

Azure Static Web Apps free tier includes:
- 100 GB bandwidth per month
- Custom domains (up to 2)
- SSL certificates (automatic)
- No charge for hosting

**Monitor Usage**:
```bash
# Check bandwidth usage
az monitor metrics list \
  --resource azlin-mobile-pwa \
  --resource-group azlin-pwa-rg \
  --resource-type Microsoft.Web/staticSites \
  --metric "BytesSent" \
  --interval PT1H
```

### Upgrade to Standard

If you exceed free tier limits:

```bash
# Upgrade to Standard tier
az staticwebapp update \
  --name azlin-mobile-pwa \
  --resource-group azlin-pwa-rg \
  --sku Standard

# Cost: $9/month + bandwidth ($0.20/GB)
```

## Next Steps

- **[Getting Started](./getting-started.md)**: Set up local development
- **[Features](./features.md)**: Learn about PWA features
- **[Architecture](./architecture.md)**: Understand technical design

## Support

- **Deployment Issues**: [GitHub Issues](https://github.com/rysweet/azlin/issues)
- **Azure Support**: [Azure Portal → Support](https://portal.azure.com/#blade/Microsoft_Azure_Support/HelpAndSupportBlade)
- **Documentation**: [Azure Static Web Apps Docs](https://docs.microsoft.com/azure/static-web-apps/)
