# Teaching Notes Generation Prompt

Generate educational content explaining what was done and why.

## Context
Resources deployed: {resources}
Connections made: {connections}
Decisions made: {decisions}
Issues encountered: {issues}

## Your Task

Create comprehensive teaching materials that help users:
1. Understand what was deployed
2. Why decisions were made
3. How resources connect
4. What they can do next
5. How to troubleshoot

## Output Format

### Section 1: Overview
High-level summary of what was built

### Section 2: Architecture
Visual and text description of how resources connect

### Section 3: Resource Details
Deep dive on each resource

### Section 4: Security & Best Practices
What security measures were applied

### Section 5: Cost Analysis
Cost breakdown and optimization tips

### Section 6: Next Steps
What to do with this infrastructure

### Section 7: Troubleshooting
Common issues and solutions

### Section 8: Learning Resources
Links to Azure documentation

## Example: App Service + Cosmos DB

```markdown
# Azure Infrastructure - Teaching Guide

## Overview

We deployed a complete web application infrastructure on Azure consisting of:
- **App Service**: Hosts your web application
- **Cosmos DB**: Globally distributed database
- **Key Vault**: Secure secret storage
- **Storage Account**: File and blob storage
- **Managed Identity**: Secure authentication without credentials

**Total deployment time**: 9 minutes
**Estimated monthly cost**: $40-60 (Basic SKUs)

## Architecture

```
┌──────────────┐
│   Internet   │
└──────┬───────┘
       │
       ▼
┌──────────────┐      ┌─────────────┐
│  App Service │──────│  Key Vault  │
│  (Web App)   │      │  (Secrets)  │
└──────┬───────┘      └──────┬──────┘
       │                     │
       │ Managed Identity    │
       │                     │
       ▼                     ▼
┌──────────────┐      ┌─────────────┐
│  Cosmos DB   │      │   Storage   │
│  (Database)  │      │   Account   │
└──────────────┘      └─────────────┘
```

## How It Works

1. **App Service** runs your application code (Node.js, Python, .NET, etc.)
2. **Managed Identity** authenticates the app to other Azure services
3. **Key Vault** stores database connection strings securely
4. **App Service** retrieves secrets from Key Vault using its identity
5. **Cosmos DB** provides globally distributed database with low latency
6. **Storage Account** stores files, images, backups, etc.

## Resource Details

### App Service (app-webapp-prod-eastus)

**What it is**: A fully managed platform for hosting web applications.

**SKU**: Basic B1
- 1 vCPU, 1.75 GB RAM
- $13/month
- Good for: Development, testing, low-traffic apps
- **Upgrade to Standard or Premium** for production workloads

**Configuration**:
- **Runtime**: Node.js 18 LTS (can change to Python, .NET, Java, etc.)
- **HTTPS Only**: Enforced for security
- **Always On**: Disabled (B1 limitation) - app may sleep after 20 min idle
- **Managed Identity**: Enabled (SystemAssigned)

**Application Settings**:
- `COSMOS_ENDPOINT`: Retrieved from Key Vault
- `COSMOS_KEY`: Retrieved from Key Vault

**Why these choices**:
- Node.js 18 LTS: Long-term support, stable
- HTTPS only: Security best practice
- Managed Identity: No credentials in code
- Key Vault references: Secrets not visible in app settings

### Cosmos DB (cosmos-webapp-prod-eastus)

**What it is**: Globally distributed, multi-model database service.

**Configuration**:
- **API**: SQL (Core) - most common, supports SQL queries
- **Consistency**: Session - balanced performance and consistency
- **Throughput**: 400 RU/s (Request Units per second)
- **Cost**: ~$24/month for 400 RU/s

**Why Cosmos DB**:
- Global distribution: Low latency worldwide
- Automatic scaling: Handles traffic spikes
- Multiple consistency levels: Choose your trade-off
- Multi-model: SQL, MongoDB, Cassandra, Gremlin, Table APIs

**Request Units (RU/s)**:
- Azure's measure of database throughput
- 400 RU/s = ~400 document reads/sec (1KB each)
- Auto-scale available: Pay for what you use

**Cost optimization**:
- Use serverless mode for sporadic workloads
- Use shared throughput for multiple containers
- Set up auto-scale for variable loads

### Key Vault (kv-webapp-prod-xxxxx)

**What it is**: Secure storage for secrets, keys, and certificates.

**Configuration**:
- **SKU**: Standard ($0 basic operations)
- **RBAC**: Enabled (modern permission model)
- **Soft Delete**: 7 days (recover deleted secrets)
- **Purge Protection**: Disabled (enable in production)

**Stored Secrets**:
- `cosmos-endpoint`: Cosmos DB connection endpoint
- `cosmos-key`: Cosmos DB primary key

**Why Key Vault**:
- **Security**: Secrets not stored in code or config files
- **Rotation**: Change secrets without redeploying app
- **Audit**: Track who accessed which secrets
- **Compliance**: Many regulations require secure secret storage

**Access Pattern**:
```
App Service → Managed Identity → Key Vault RBAC → Secret
```

No credentials needed! App Service uses its identity.

### Storage Account (stwebappprodxxxxx)

**What it is**: Scalable storage for files, blobs, queues, tables.

**Configuration**:
- **SKU**: Standard_LRS (Locally Redundant)
- **Replication**: 3 copies within same datacenter
- **Cost**: $1-5/month (depends on usage)

**Security**:
- HTTPS only
- TLS 1.2 minimum
- Public blob access disabled
- Requires authentication for all access

**Use cases**:
- User uploaded files (images, documents)
- Application logs and diagnostics
- Static website hosting
- Backup storage

**Replication options**:
- **LRS**: Cheapest, local redundancy
- **GRS**: Geographic redundancy (different region)
- **ZRS**: Zone redundancy (different datacenter, same region)
- **GZRS**: Geographic + zone redundancy

## Security & Best Practices

### ✅ Security Measures Applied

1. **Managed Identity**
   - App Service has system-assigned identity
   - No credentials stored in code or config
   - Azure handles authentication automatically

2. **Key Vault Integration**
   - All secrets stored in Key Vault
   - App Service reads secrets using managed identity
   - Secrets never exposed in app settings

3. **HTTPS Enforcement**
   - All services enforce HTTPS
   - HTTP traffic redirected to HTTPS
   - TLS 1.2 minimum

4. **RBAC Authorization**
   - Key Vault uses RBAC (not legacy access policies)
   - Principle of least privilege
   - App Service has "Key Vault Secrets User" role only

5. **Network Security**
   - Public blob access disabled on storage
   - Can add private endpoints for fully private setup

### 🔒 Additional Hardening (Optional)

For production environments, consider:

1. **Private Endpoints**
   - Deploy resources in VNet
   - No public internet access
   - Requires VPN or ExpressRoute

2. **Network Rules**
   - Restrict Key Vault to specific IPs/VNets
   - Storage account firewall rules

3. **Advanced Threat Protection**
   - Enable for Cosmos DB and Storage
   - Detects anomalous access patterns

4. **Diagnostic Logging**
   - Send logs to Log Analytics
   - Monitor for security events

## Cost Analysis

### Monthly Cost Breakdown (Approximate)

| Resource | SKU | Cost/Month |
|----------|-----|------------|
| App Service | B1 | $13 |
| App Service Plan | B1 | (included above) |
| Cosmos DB | 400 RU/s | $24 |
| Storage Account | Standard LRS | $1-5 |
| Key Vault | Standard | $0 (basic ops) |
| **Total** | | **~$40-45** |

**Actual costs vary by**:
- Region (some more expensive)
- Usage (data transfer, operations)
- Retention (backups, logs)

### Cost Optimization Tips

1. **App Service**:
   - Use Free or Shared tier for dev/test
   - Use consumption-based Functions for event-driven workloads
   - Enable auto-scale to handle peaks efficiently

2. **Cosmos DB**:
   - Use serverless mode for unpredictable workloads
   - Share throughput across containers
   - Use Time-to-Live (TTL) to auto-delete old data
   - Consider Azure SQL if don't need global distribution

3. **Storage**:
   - Use cool/archive tiers for infrequently accessed data
   - Set up lifecycle management to auto-tier
   - Delete old logs and backups

4. **General**:
   - Use Azure Cost Management to track spending
   - Set up budget alerts
   - Delete unused resources promptly

## Next Steps

### 1. Deploy Your Application

```bash
# Package your app
zip -r app.zip .

# Deploy to App Service
az webapp deployment source config-zip \
  --resource-group rg-webapp-prod-eastus \
  --name app-webapp-prod-eastus \
  --src app.zip
```

### 2. Configure Custom Domain

```bash
# Add custom domain
az webapp config hostname add \
  --webapp-name app-webapp-prod-eastus \
  --resource-group rg-webapp-prod-eastus \
  --hostname www.example.com

# Add SSL certificate (free managed certificate)
az webapp config ssl bind \
  --name app-webapp-prod-eastus \
  --resource-group rg-webapp-prod-eastus \
  --certificate-thumbprint auto \
  --ssl-type SNI
```

### 3. Set Up CI/CD

Use GitHub Actions, Azure DevOps, or other CI/CD:

```yaml
# .github/workflows/deploy.yml
name: Deploy to Azure
on: [push]
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v2
      - uses: azure/webapps-deploy@v2
        with:
          app-name: app-webapp-prod-eastus
          publish-profile: ${{ secrets.AZURE_PUBLISH_PROFILE }}
```

### 4. Add Monitoring

```bash
# Enable Application Insights
az monitor app-insights component create \
  --app myapp-insights \
  --location eastus \
  --resource-group rg-webapp-prod-eastus \
  --application-type web

# Link to App Service
az webapp config appsettings set \
  --resource-group rg-webapp-prod-eastus \
  --name app-webapp-prod-eastus \
  --settings APPINSIGHTS_INSTRUMENTATIONKEY=<key>
```

### 5. Configure Cosmos DB

```bash
# Create database and container
az cosmosdb sql database create \
  --account-name cosmos-webapp-prod-eastus \
  --resource-group rg-webapp-prod-eastus \
  --name myapp-db

az cosmosdb sql container create \
  --account-name cosmos-webapp-prod-eastus \
  --resource-group rg-webapp-prod-eastus \
  --database-name myapp-db \
  --name users \
  --partition-key-path "/userId"
```

## Troubleshooting

### App Service won't start

**Check logs**:
```bash
az webapp log tail \
  --resource-group rg-webapp-prod-eastus \
  --name app-webapp-prod-eastus
```

**Common issues**:
- Missing npm/pip dependencies
- Environment variables not set
- Port binding (use process.env.PORT)

### Can't connect to Cosmos DB

**Verify connection settings**:
```bash
az webapp config appsettings list \
  --resource-group rg-webapp-prod-eastus \
  --name app-webapp-prod-eastus
```

**Check Key Vault access**:
```bash
az role assignment list \
  --scope /subscriptions/.../resourceGroups/rg-webapp-prod-eastus/providers/Microsoft.KeyVault/vaults/kv-webapp-prod
```

**Test connection**:
```javascript
const cosmos = require('@azure/cosmos');
const endpoint = process.env.COSMOS_ENDPOINT;
const key = process.env.COSMOS_KEY;
const client = new cosmos.CosmosClient({ endpoint, key });
```

### Storage access denied

**Check CORS settings** (for browser uploads):
```bash
az storage cors add \
  --services b \
  --methods GET POST PUT \
  --origins * \
  --allowed-headers * \
  --exposed-headers * \
  --max-age 3600 \
  --account-name stwebappprod
```

**Use SAS tokens** for temporary access:
```bash
az storage container generate-sas \
  --account-name stwebappprod \
  --name mycontainer \
  --permissions rl \
  --expiry 2025-12-31
```

## Learning Resources

### Official Documentation
- [App Service](https://learn.microsoft.com/azure/app-service/)
- [Cosmos DB](https://learn.microsoft.com/azure/cosmos-db/)
- [Key Vault](https://learn.microsoft.com/azure/key-vault/)
- [Managed Identities](https://learn.microsoft.com/azure/active-directory/managed-identities-azure-resources/)

### Tutorials
- [Deploy Node.js app to App Service](https://learn.microsoft.com/azure/app-service/quickstart-nodejs)
- [Build a web app with Cosmos DB](https://learn.microsoft.com/azure/cosmos-db/sql/tutorial-develop-mongodb-nodejs)
- [Use Key Vault in App Service](https://learn.microsoft.com/azure/app-service/app-service-key-vault-references)

### Best Practices
- [Azure Security Best Practices](https://learn.microsoft.com/azure/security/fundamentals/best-practices-and-patterns)
- [Cost Optimization](https://learn.microsoft.com/azure/cost-management-billing/costs/cost-mgt-best-practices)
- [App Service Best Practices](https://learn.microsoft.com/azure/app-service/app-service-best-practices)

---

**Generated by azlin doit** - Autonomous Azure Infrastructure Agent
```

## Teaching Principles

1. **Explain the "Why"**: Don't just say what was done, explain why
2. **Visual Aids**: Use ASCII diagrams for architecture
3. **Practical Examples**: Show actual commands to run
4. **Troubleshooting**: Anticipate common problems
5. **Next Steps**: Give clear path forward
6. **Cost Transparency**: Always mention cost implications
7. **Security Context**: Explain security decisions
8. **Learning Links**: Point to official documentation
