# azlin context

Manage kubectl-style contexts for multi-tenant Azure access.

Contexts allow you to switch between different Azure subscriptions
and tenants without changing environment variables or config files.

Each context contains:
- subscription_id: Azure subscription ID
- tenant_id: Azure tenant ID
- auth_profile: Optional service principal profile


EXAMPLES:
    # List all contexts
    $ azlin context list

    # Show current context
    $ azlin context current

    # Switch to a context
    $ azlin context use production

    # Create new context
    $ azlin context create staging \
        --subscription xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx \
        --tenant yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy

    # Create context with auth profile
    $ azlin context create prod \
        --subscription xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx \
        --tenant yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy \
        --auth-profile prod-sp

    # Rename context
    $ azlin context rename old-name new-name

    # Delete context
    $ azlin context delete staging

    # Migrate from legacy config
    $ azlin context migrate


## Description

Manage kubectl-style contexts for multi-tenant Azure access.
Contexts allow you to switch between different Azure subscriptions
and tenants without changing environment variables or config files.
Each context contains:
- subscription_id: Azure subscription ID
- tenant_id: Azure tenant ID
- auth_profile: Optional service principal profile

EXAMPLES:
# List all contexts
$ azlin context list
# Show current context
$ azlin context current
# Switch to a context
$ azlin context use production
# Create new context
$ azlin context create staging \
--subscription xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx \
--tenant yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy
# Create context with auth profile
$ azlin context create prod \
--subscription xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx \
--tenant yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy \
--auth-profile prod-sp
# Rename context
$ azlin context rename old-name new-name
# Delete context
$ azlin context delete staging
# Migrate from legacy config
$ azlin context migrate

## Usage

```bash
azlin context
```

## Subcommands

### create

Create a new context.

Creates a new context with the specified subscription and tenant IDs.
Optionally associates an authentication profile for service principal auth.


EXAMPLES:
    # Basic context
    $ azlin context create staging \
        --subscription xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx \
        --tenant yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy

    # With auth profile
    $ azlin context create prod \
        --subscription xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx \
        --tenant yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy \
        --auth-profile prod-sp

    # With description and set as current
    $ azlin context create dev \
        --subscription xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx \
        --tenant yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy \
        --description "Development environment" \
        --set-current


**Usage:**
```bash
azlin context create NAME [OPTIONS]
```

**Options:**
- `--subscription`, `--subscription-id` - Azure subscription ID (UUID)
- `--tenant`, `--tenant-id` - Azure tenant ID (UUID)
- `--auth-profile` - Service principal auth profile name (optional)
- `--description` - Human-readable description (optional)
- `--set-current` - Set as current context after creation
- `--config` - Custom config file path

### current

Show current active context.

Displays the name and details of the currently active context.


EXAMPLES:
    $ azlin context current
    $ azlin context current --config ~/custom-config.toml


**Usage:**
```bash
azlin context current [OPTIONS]
```

**Options:**
- `--config` - Custom config file path

### delete

Delete a context.

Removes the specified context from the configuration. If the context
is currently active, the current context will be unset.


EXAMPLES:
    $ azlin context delete staging
    $ azlin context delete old-context --force
    $ azlin context delete test --config ~/custom-config.toml


**Usage:**
```bash
azlin context delete NAME [OPTIONS]
```

**Options:**
- `--config` - Custom config file path
- `--force`, `-f` - Skip confirmation prompt

### list

List all available contexts.

Shows all configured contexts with their subscription and tenant IDs.
The current context is marked with an asterisk (*).


EXAMPLES:
    $ azlin context list
    $ azlin context list --config ~/custom-config.toml


**Usage:**
```bash
azlin context list [OPTIONS]
```

**Options:**
- `--config` - Custom config file path

### migrate

Migrate from legacy config format.

Checks for legacy subscription_id and tenant_id fields in config.toml
and creates a 'default' context from them. This provides backward
compatibility with existing azlin configurations.

The legacy fields are preserved for backward compatibility with older
azlin versions.


EXAMPLES:
    $ azlin context migrate
    $ azlin context migrate --config ~/custom-config.toml
    $ azlin context migrate --force


**Usage:**
```bash
azlin context migrate [OPTIONS]
```

**Options:**
- `--config` - Custom config file path
- `--force`, `-f` - Force migration even if contexts exist

### rename

Rename a context.

Changes the name of an existing context. If the context is currently
active, the current context pointer is updated automatically.


EXAMPLES:
    $ azlin context rename staging stage
    $ azlin context rename old-prod production
    $ azlin context rename dev development --config ~/custom-config.toml


**Usage:**
```bash
azlin context rename OLD_NAME NEW_NAME [OPTIONS]
```

**Options:**
- `--config` - Custom config file path

### use

Switch to a different context.

Sets the specified context as the current active context. All subsequent
azlin commands will use this context's subscription and tenant.


EXAMPLES:
    $ azlin context use production
    $ azlin context use dev --config ~/custom-config.toml


**Usage:**
```bash
azlin context use NAME [OPTIONS]
```

**Options:**
- `--config` - Custom config file path
