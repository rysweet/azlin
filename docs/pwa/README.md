# Azlin Mobile PWA

**Manage your Azure Linux VMs from your iPhone.**

Azlin Mobile PWA provides full VM management capabilities through a Progressive Web App that installs on your iPhone home screen. No backend server required - the app communicates directly with Azure REST APIs using your Azure credentials.

## Key Features

- **VM Management**: Create, start, stop, delete, and monitor VMs
- **Tmux Integration**: View tmux session snapshots and send commands without keeping connections open
- **Private IP Support**: Works with VMs behind Azure Bastion (no public IPs needed)
- **Cost Tracking**: Real-time cost monitoring and budget alerts
- **Installable**: Add to iPhone home screen for native app experience
- **Offline-Ready**: Service worker caching for instant loads

## Quick Start

**Zero-Config Experience**: If ye've configured azlin already, the PWA sets itself up automatically!

```bash
# Clone and install
git clone https://github.com/rysweet/azlin.git
cd azlin/pwa
npm install

# Zero-config start (if azlin is configured)
npm start
# ✓ Automatically pulls config from Azure CLI and azlin
# ✓ Only CLIENT_ID needs manual setup (one-time)

# Manual config (if needed)
cp .env.example .env
# Edit .env with your Azure credentials

# Build for production
npm run build
```

**What happens automatically:**
- Tenant ID and Subscription ID from `az account show`
- Bastion configuration from `~/.azlin/config.json`
- Clear feedback showing where each value came from

**What needs one-time manual setup:**
- Azure AD Client ID (requires app registration - see [Getting Started](./getting-started.md))

Visit on your iPhone and tap "Add to Home Screen".

## Architecture

Azlin Mobile PWA is a React-based Progressive Web App that:

1. **Authenticates** using Azure AD OAuth2 (device code flow for mobile)
2. **Communicates** directly with Azure REST APIs (no backend server)
3. **Executes** commands via Azure Run Command API
4. **Monitors** tmux sessions through periodic snapshots
5. **Caches** data locally using IndexedDB and service workers

For detailed architecture, see [Architecture Documentation](./architecture.md).

## Documentation

- **[Getting Started](./getting-started.md)** - Installation and authentication setup
- **[Features Guide](./features.md)** - Complete feature documentation with examples
- **[Architecture](./architecture.md)** - Technical architecture and API integration
- **[Deployment](./deployment.md)** - Deploy to Azure Static Web Apps

## Requirements

- iOS 16+ or iPadOS 16+ (for PWA support)
- Node.js 18+ (for development)
- Azure subscription with VM permissions
- Azure Bastion (recommended for private IP VMs)

## Security

- All authentication uses Azure AD OAuth2
- No passwords stored locally
- Refresh tokens secured in iOS Keychain (via PWA)
- Azure RBAC controls VM access
- All API calls use HTTPS

## License

MIT License - see [LICENSE](../../LICENSE) for details.

## Support

- **Issues**: [GitHub Issues](https://github.com/rysweet/azlin/issues)
- **Discussions**: [GitHub Discussions](https://github.com/rysweet/azlin/discussions)
- **Documentation**: [https://rysweet.github.io/azlin](https://rysweet.github.io/azlin)
