# azlin doit examples

Show example deployment requests.

## Synopsis

```bash
azlin doit examples
```

## Description

Displays curated examples of natural language deployment requests with expected outcomes.

## Example Categories

### Web Applications

```bash
# Simple static site
azlin doit deploy "static website with CDN"

# Dynamic web app
azlin doit deploy "web app with SQL database"

# Full stack
azlin doit deploy "React app with Node.js API and PostgreSQL"
```

### Microservices

```bash
# Container platform
azlin doit deploy "AKS cluster with monitoring"

# API gateway
azlin doit deploy "API Management with backend services"

# Event-driven
azlin doit deploy "Service Bus, Functions, and storage"
```

### Data & Analytics

```bash
# NoSQL database
azlin doit deploy "Cosmos DB with MongoDB API"

# Data warehouse
azlin doit deploy "Synapse Analytics with storage"

# Real-time analytics
azlin doit deploy "Event Hub with Stream Analytics"
```

### AI & ML

```bash
# Machine learning
azlin doit deploy "ML workspace with compute cluster"

# Cognitive services
azlin doit deploy "Computer Vision and Speech services"
```

### Security & Networking

```bash
# Secure infrastructure
azlin doit deploy "VNet with private endpoints and firewall"

# Secrets management
azlin doit deploy "KeyVault with managed identities"
```

## Related Commands

- [azlin doit deploy](deploy.md) - Deploy infrastructure
