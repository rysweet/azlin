# Multi-Tenant Context Management

azlin supports kubectl-style context management for switching between multiple Azure subscriptions, tenants and resource groups.

## What a Context Is

A context is a named file recording defaults for a set of Azure work:

| Field             | Applied by azlin | Effect                                                                   |
| ----------------- | ---------------- | ------------------------------------------------------------------------ |
| `subscription_id` | yes              | Every command runs against this subscription                             |
| `resource_group`  | yes              | Default resource group when `--resource-group` is not passed             |
| `tenant_id`       | yes (checked)    | Commands refuse to run if the Azure CLI is signed in to a different one  |
| `region`          | yes              | Default region for `azlin new` and the `list --quota` read                |
| `key_vault_name`  | no (recorded)    | Recorded for reference; no command reads it yet                          |

Fields marked "no" are stored and shown, but do not change command behaviour.

## Quick Start

```bash
# Create contexts for different environments
azlin context create dev \
  --subscription-id xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx \
  --tenant-id yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy \
  --resource-group dev-rg

azlin context create prod \
  --subscription-id zzzzzzzz-zzzz-zzzz-zzzz-zzzzzzzzzzzz \
  --tenant-id yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy \
  --resource-group prod-rg

# List all contexts (the active one is marked with *)
azlin context list

# Switch between contexts
azlin context use dev
azlin list          # VMs in the dev subscription's dev-rg

azlin context use prod
azlin list          # VMs in the prod subscription's prod-rg

# Check the current context and the subscription actually in force
azlin context show
```

## How Switching Works

`azlin context use <name>` runs `az account set --subscription <id>`, then re-reads
`az account show` to confirm the switch took effect:

```
$ azlin context use prod
Switched to context 'prod' (Azure CLI subscription: zzzzzzzz-zzzz-zzzz-zzzz-zzzzzzzzzzzz)
Note: this sets the Azure CLI's default subscription, which also affects plain 'az' commands.
```

Two consequences worth knowing:

- **The switch is global to the Azure CLI.** azlin invokes `az` for every Azure
  operation, so moving the CLI's active subscription is what makes the context
  apply. Plain `az` commands in your shell follow it too.
- **A switch that cannot be performed is not recorded.** If `az account set`
  fails — not logged in, no access to that subscription, `az` not installed —
  the command exits non-zero and the active context is left unchanged. azlin
  never reports a switch it did not make.

Every command re-applies the active context before talking to Azure, so if
something else repoints the CLI in the meantime, azlin moves it back (and
refuses to run if it cannot).

## Checking What Is Actually in Force

`azlin context show` prints the context file *and* the subscription the Azure CLI
reports right now, so a mismatch is visible rather than assumed:

```
$ azlin context show
Current context: prod
name = "prod"
resource_group = "prod-rg"
subscription_id = "zzzzzzzz-zzzz-zzzz-zzzz-zzzzzzzzzzzz"

Effective subscription (az account show): xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
MISMATCH: this context pins zzzzzzzz-…, but the Azure CLI is on xxxxxxxx-….
azlin will switch the CLI to zzzzzzzz-… before running any Azure command, and
will refuse to run if the switch does not take effect.
```

## Resource-Group and Region Precedence

For any command, the resource group is resolved in this order — the first that
applies wins:

1. `--resource-group <rg>` passed to the command
2. `resource_group` in the active context
3. `default_resource_group` from `azlin config`

Region follows the same shape:

1. `--region <name>` passed to the command
2. `region` in the active context
3. `default_region` from `azlin config`

## All Commands

### `azlin context list`

List all contexts. The active one is marked with `*`.

### `azlin context show` (alias: `current`)

Show the active context, its file contents, and the effective Azure CLI subscription.

### `azlin context use <name>` (alias: `switch`)

Switch to a context. Sets the Azure CLI's active subscription and verifies it.
Fails without recording anything if the switch cannot be performed.

A context with no `subscription_id` is selected without an Azure call, and says
so — selecting it cannot change which subscription commands run against.

### `azlin context create <name>`

Create a context.

**Options:**

- `--subscription-id <uuid>` — Azure subscription ID
- `--tenant-id <uuid>` — Azure tenant ID
- `--resource-group <name>` — default resource group for this context
- `--region <name>` — default region for VM creation in this context
- `--key-vault-name <name>` — recorded for reference

### `azlin context delete <name>`

Delete a context. If it was active, the active-context marker is cleared.

### `azlin context rename <old-name> <new-name>`

Rename a context, preserving its contents and its active status.

### `azlin context migrate`

Create a `default` context from the current `az account show` output plus your
existing `default_resource_group` / `default_region` config.

## Listing Across Contexts

`azlin list --all-contexts` queries each context's own subscription explicitly
(`az vm list --subscription <id>`), without changing the CLI's active
subscription. Each block header names the subscription and resource group the
rows below came from:

```
── context: dev (subscription: xxxxxxxx-…, rg: dev-rg) — 4 VMs ──
── context: prod (subscription: zzzzzzzz-…, rg: prod-rg) — 6 VMs ──
```

A context with no `subscription_id` is listed from whichever subscription the
CLI is on, and its header says so with `[inherited — context pins none]`.

When the listing spans more than one subscription, the bastion, tmux, health and
process columns are omitted: those lookups are scoped to a single subscription
and cannot be attributed correctly across several. `--show-procs` is included
because it builds an ARM resource id from the active subscription, which under
`--all-contexts` would name a same-named VM in the wrong one.

`--contexts <pattern>` filters which contexts are included (`*` acts as a
substring wildcard).

## Storage

Contexts live under azlin's state directory — `$AZLIN_CONFIG_DIR` if set,
otherwise `~/.azlin`:

```
~/.azlin/
├── active-context          # a single line: the selected context's name
└── contexts/
    ├── dev.toml
    └── prod.toml
```

Each context file is plain TOML:

```toml
name = "prod"
subscription_id = "zzzzzzzz-zzzz-zzzz-zzzz-zzzzzzzzzzzz"
tenant_id = "yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy"
resource_group = "prod-rg"
region = "westus2"
```

## Security

- **No secrets stored** — contexts hold subscription/tenant IDs and names only.
- **Name sanitization** — context names are restricted to alphanumeric plus
  hyphen/underscore, and path traversal is rejected.
- **Tenant check** — if a context pins `tenant_id` and the Azure CLI is signed
  in to a different tenant, commands refuse to run rather than acting on a
  subscription reached through unexpected credentials.

## Troubleshooting

### `context use` fails with "Did not switch to context …"

The Azure CLI could not be moved onto that context's subscription. The active
context is unchanged — nothing was switched, and no command will act as if it
had been. Check:

```bash
az account list --output table   # do you have access to that subscription?
az login                          # or log in to the right tenant
```

### A command refuses to run, reporting a subscription mismatch

`az account set` reported success but `az account show` still shows a different
subscription. This usually means the subscription ID in the context does not
exist in the cloud/tenant you are signed in to. Verify with
`az account list --output table`.

### "Active context '<name>' is selected but its file cannot be read"

The `active-context` marker names a context whose file is missing or malformed.
Run `azlin context list` to see what exists and `azlin context use <name>` to
select one of them.

### A resource group error mentions the active context

The active context does not set a `resource_group`. Either pass
`--resource-group <rg>`, recreate the context with
`azlin context create <name> --resource-group <rg>`, or set the global default
with `azlin config set default_resource_group <rg>`.
