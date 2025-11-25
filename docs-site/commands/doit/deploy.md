# azlin doit deploy

Deploy Azure infrastructure from natural language request.

## Synopsis

```bash
azlin doit deploy "<request>" [OPTIONS]
```

## Description

AI-powered autonomous deployment that:
1. Parses natural language into concrete goals
2. Plans resource dependencies and order
3. Executes deployment using Azure CLI
4. Verifies each resource creation
5. Generates Terraform and Bicep templates
6. Provides teaching materials

## Options

| Option | Description | Default |
|--------|-------------|---------|
| `-o, --output-dir PATH` | Output directory for generated artifacts | `./doit-output` |
| `-m, --max-iterations INTEGER` | Maximum execution iterations | `50` |
| `--dry-run` | Show plan without deploying | `false` |
| `-q, --quiet` | Reduce output verbosity | `false` |
| `-h, --help` | Show help | - |

## Examples

### Simple web app
```bash
azlin doit deploy "web app with database"
```

### Preview before deploying
```bash
azlin doit deploy "App Service with Cosmos DB" --dry-run
```

### Complex infrastructure
```bash
azlin doit deploy "microservices with API Management, KeyVault, Storage, Cosmos DB in eastus" -o ./infra
```

### Specific requirements
```bash
azlin doit deploy "web app in eastus with SQL database, Standard tier"
```

## Output

The command generates:
- Deployed Azure resources
- Terraform templates (`terraform/`)
- Bicep templates (`bicep/`)
- Deployment documentation
- Architecture diagrams

## Related Commands

- [azlin doit list](list.md) - List created resources
- [azlin doit cleanup](cleanup.md) - Clean up resources
