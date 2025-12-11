# azlin doit

Autonomous Azure infrastructure deployment.

Use natural language to describe your infrastructure needs,
and doit will autonomously deploy it using Azure CLI.


## Description

Autonomous Azure infrastructure deployment.
Use natural language to describe your infrastructure needs,
and doit will autonomously deploy it using Azure CLI.

## Usage

```bash
azlin doit
```

## Subcommands

### cleanup

Delete all doit-created resources.

By default, prompts for confirmation before deleting.
Resources are deleted in dependency order (data resources last).

Examples:

    azlin doit cleanup

    azlin doit cleanup --force

    azlin doit cleanup --dry-run


**Usage:**
```bash
azlin doit cleanup [OPTIONS]
```

**Options:**
- `--force`, `-f` - Skip confirmation prompt
- `--dry-run` - Show what would be deleted without deleting
- `--username`, `-u` - Azure username to filter by (defaults to current user)

### delete

Alias for cleanup - delete all doit-created resources.

**Usage:**
```bash
azlin doit delete [OPTIONS]
```

**Options:**
- `--force`, `-f` - Skip confirmation prompt
- `--dry-run` - Show what would be deleted
- `--username`, `-u` - Azure username to filter by

### deploy

Deploy infrastructure from natural language request.

Examples:

    azlin doit deploy "Give me App Service with Cosmos DB"

    azlin doit deploy "Create App Service, Cosmos DB, API Management, Storage, and KeyVault all connected"

    azlin doit deploy "Deploy a web app with database in eastus" --dry-run

The agent will:
1. Parse your request into concrete goals
2. Determine dependencies between resources
3. Execute deployment using Azure CLI
4. Verify each step succeeded
5. Generate production-ready Terraform and Bicep
6. Provide teaching materials explaining what was done


**Usage:**
```bash
azlin doit deploy REQUEST [OPTIONS]
```

**Options:**
- `--output-dir`, `-o` - Output directory for generated artifacts
- `--max-iterations`, `-m` - Maximum execution iterations
- `--dry-run` - Show what would be deployed without actually deploying
- `--quiet`, `-q` - Reduce output verbosity

### destroy

Alias for cleanup - delete all doit-created resources.

**Usage:**
```bash
azlin doit destroy [OPTIONS]
```

**Options:**
- `--force`, `-f` - Skip confirmation prompt
- `--dry-run` - Show what would be deleted
- `--username`, `-u` - Azure username to filter by

### examples

Show example requests.

### list

List all resources created by doit.

Shows all Azure resources tagged with azlin-doit-owner.
By default, lists resources for the current Azure user.

Examples:

    azlin doit list

    azlin doit list --username user@example.com


**Usage:**
```bash
azlin doit list [OPTIONS]
```

**Options:**
- `--username`, `-u` - Azure username to filter by (defaults to current user)

### show

Show detailed information about a doit-created resource.

Provide the full Azure resource ID to see detailed information.

Examples:

    azlin doit show /subscriptions/.../resourceGroups/rg-name/providers/Microsoft.Web/sites/my-app


**Usage:**
```bash
azlin doit show RESOURCE_ID
```

### status

Check status of a deployment session.

**Usage:**
```bash
azlin doit status [OPTIONS]
```

**Options:**
- `--session`, `-s` - Session ID to check status
