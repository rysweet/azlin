# azlin list

**Discover and filter VMs across resource groups and contexts**

## Description

The `azlin list` command displays all azlin-managed VMs in table format, showing VM name, status, IP address, region, size, vCPU count, and optionally regional vCPU quota and tmux session information. It supports filtering by tags, scanning across all resource groups, and querying multiple Azure contexts for multi-tenant scenarios.

**Key features:**
- Fast listing of VMs in configured resource group (default)
- Filter by tags for organizational queries
- Show the region's vCPU usage and quota limits with `-q` (azlin prints Azure's own figures; it does not compute remaining capacity for you)
- Display active tmux sessions per VM
- Multi-context support for complex Azure setups
- Prevent VM name truncation with `--wide` flag

## Usage

```bash
azlin list [OPTIONS]
```

## Options

| Option | Type | Description |
|--------|------|-------------|
| `--resource-group, --rg TEXT` | Name | Resource group to list VMs from (default: from config) |
| `--config PATH` | File | Path to custom config file (default: `~/.azlin/config.toml`) |
| `--all`, `--include-stopped` | Flag | Include stopped/deallocated VMs in the listed resource group (default: running only). Not the same as `-a` |
| `--tag TEXT` | Key or Key=Value | Filter VMs by tag (format: `key` or `key=value`) |
| `-q, --quota` | Flag | Append a `vCPU Quota:` section: the region's `az vm list-usage` vCPU rows, printed as `az` formats them (default: off) |
| `--show-tmux [true\|false]` | Flag | Show/hide active tmux sessions (default: show). `--no-tmux` is shorthand for `--show-tmux false` |
| `--with-health` | Flag | Add the `Agent`, `CPU%`, `Mem%` and `Disk%` columns, collected over SSH |
| `--show-procs` | Flag | Add the `Procs` column — top processes by memory, collected over SSH. **Table output only** |
| `--with-latency` | Flag | Add the `Latency` column — a TCP connect time to port 22, measured from this machine |
| `--vm-pattern TEXT` | Glob Pattern | Filter VMs by name pattern |
| `-c, --compact` | Flag | Narrower columns for constrained terminals |
| `--no-cache` | Flag | Skip the cache and fetch fresh data |
| `-a, --show-all-vms` | Flag | Scan ALL resource groups (expensive operation). Still running-only — combine with `--all` for stopped VMs too |
| `--all-contexts` | Flag | List VMs across all configured contexts (requires context setup) |
| `--contexts TEXT` | Glob Pattern | List VMs from contexts matching pattern (e.g., `prod*`, `dev-*`) |
| `-w, --wide` | Flag | **NEW in v0.3.2** - Prevent VM name truncation in output |
| `-h, --help` | Flag | Show command help and exit |

`-o, --output {table,json,csv}` is a global azlin flag and applies here:
`azlin -o json list`. Tmux and health data are *collected* in every output
format and *emitted* in all three. Process data is collected in every format but
only rendered in the table — see [Limitations](#limitations).

### JSON is an object, not an array

!!! warning "Breaking change"
    `azlin -o json list` previously emitted a bare array of VM objects. It now
    emits an object: the VM array moved under a `vms` key, alongside a `filters`
    object reporting how many rows each filter removed.

    ```json
    {
      "filters": {
        "dropped_by_pattern": 0,
        "dropped_by_tag": 0,
        "hidden_not_running": 4
      },
      "vms": [ /* per-VM objects, unchanged */ ]
    }
    ```

    **Migrate `jq '.[]'` to `jq '.vms[]'`.** Per-VM objects are unchanged — same
    keys, same types, same values. Keys serialise alphabetically.

    `filters` is **always present with all three keys**, including when nothing
    was hidden, so a consumer never has to distinguish a missing key from `0`.

    Watch for `jq 'length'`, which returns `2` against the envelope — the key
    count, not a VM count. It exits `0`, so nothing flags it. Use
    `jq '.vms | length'`.

`-o csv` is unaffected: stdout keeps the same header and rows. When a filter
dropped rows, the disclosure is written to **stderr** — the same
`Note: {n} hidden (stopped/deallocated).` line the `-o json` run writes, plus
the `--all` remedy when the running filter was the cause. Nothing is written
when nothing was dropped. A consumer that needs the counts as data should read
them from the `-o json` `filters` envelope rather than parse stderr.

See [Filter Disclosure](../../vm-lifecycle/filter-disclosure.md) for the full
contract, counter semantics, and migration table.

## Examples

### Basic Listing

```bash
# List running VMs in default resource group
azlin list

# List all VMs including stopped ones
azlin list --all

# List VMs in specific resource group
azlin list --rg my-resource-group
```

### Wide Format (No Truncation)

```bash
# Show full VM names without truncation (NEW in v0.3.2)
azlin list --wide
azlin list -w

# Useful for long VM names
azlin list --wide --all
```

### Tag-Based Filtering

```bash
# Filter by tag key (any value)
azlin list --tag environment

# Filter by exact tag key=value
azlin list --tag environment=production
azlin list --tag team=backend
azlin list --tag project=ml-training

# Combine with --all to include stopped VMs
azlin list --tag environment=dev --all
```

### Quota and Session Information

```bash
# Add the vCPU quota section (off by default)
azlin list -q
azlin list --quota

# Hide tmux session information for faster output
azlin list --no-tmux

# Quota section without the tmux probes
azlin list -q --no-tmux
```

### Cross-Resource Group Scanning

```bash
# List ALL VMs across ALL resource groups (expensive!)
azlin list --show-all-vms
azlin list -a

# Combine with filters
azlin list -a --tag environment=production
```

`--show-all-vms` also widens the reach of the enrichment columns. Bastions are
discovered in every resource group that contains a running VM with no public IP,
so tmux, health and process data are collected for private VMs in *all* the
listed resource groups — not only the first one. That means a wide listing runs
remote commands against a correspondingly wide set of hosts; see
[Limitations](#limitations).

### Multi-Context Queries

```bash
# List VMs across all configured contexts
azlin list --all-contexts

# List VMs from production contexts
azlin list --contexts "prod*"

# List VMs from development contexts
azlin list --contexts "*-dev"

# Include stopped VMs across contexts
azlin list --contexts "prod*" --all
```

### Combined Filters

```bash
# Production VMs, including stopped, with full names
azlin list --tag environment=production --all --wide

# Development VMs with the quota footer
azlin list --tag environment=dev -q

# All VMs in specific RG with full details
azlin list --rg my-rg --all --wide
```

## Output Format

The `azlin list` command displays a table with the following columns:

| Column | Description |
|--------|-------------|
| **Session** | Named session with OS icon prefix (e.g., 🟠 for Ubuntu, 🐧 for Linux, 🪟 for Windows) |
| **Tmux** | Active tmux sessions, comma-separated (default; hide with `--no-tmux`). `-` when the VM reported none |
| **VM Name** | VM identifier (only in `--wide` mode) |
| **OS** | Operating system name and version (e.g., Ubuntu 25.10, Ubuntu 22.04 LTS) |
| **Status** | Running, Stopped, Deallocated, etc. |
| **IP** | Public IP (or private IP with "Bast" for bastion-only) |
| **Region** | Azure region (e.g., eastus, westus2) |
| **SKU** | Azure VM SKU (only in `--wide` mode) |
| **CPU** | Number of virtual CPUs |
| **Mem** | Memory in GB |
| **Latency** | TCP connect time to port 22 (only with `--with-latency`). No measurement renders as `-` in the table, an empty field in CSV and `null` in JSON |
| **Agent**, **CPU%**, **Mem%**, **Disk%** | Four separate columns, added together by `--with-health`: agent status and the three usage percentages |
| **Procs** | Top processes by memory (only with `--show-procs`). Table output only |

**Footer:** a one-line summary — `Total: <N> VMs | <M> running`, with
`| <K> tmux sessions` appended when any sessions were found. It counts VMs, not
vCPUs. When a filter dropped rows, the line gains one clause per filter that
actually dropped something, e.g.
`Total: 2 VMs | 2 running | 4 hidden (stopped/deallocated)`, followed by
`Hidden VMs still bill for attached storage. Run 'azlin list --all' to include them.`
when the running-only default was the cause. See
[Filter Disclosure](../../vm-lifecycle/filter-disclosure.md).

### Example Output

```
┏━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┳━━━━━━━━━┳━━━━━━━━━━━━━━━━━━┳━━━━━━━━━┳━━━━━┳━━━━━━┓
┃ Session        ┃ OS               ┃ Status  ┃ IP               ┃ Region  ┃ CPU ┃  Mem ┃
┡━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━━━╇━━━━━━━━━╇━━━━━━━━━━━━━━━━━━╇━━━━━━━━━╇━━━━━╇━━━━━━┩
│ 🟠 ml-train    │ Ubuntu 25.10     │ Running │ 20.123.45.67     │ eastus  │  32 │ 64GB │
│ 🟠 backend-dev │ Ubuntu 22.04 LTS │ Running │ 20.123.45.68     │ westus2 │  16 │ 32GB │
│ 🪟 webapp      │ Windows Server   │ Running │ 20.123.45.69     │ eastus  │   2 │  4GB │
│ 🟠 -           │ Ubuntu 24.04 LTS │ Stopped │ -                │ eastus  │   2 │  4GB │
└────────────────┴──────────────────┴─────────┴──────────────────┴─────────┴─────┴──────┘

Total: 4 VMs | 3 running
```

## Understanding Quota Display

`-q, --quota` appends a `vCPU Quota:` section after the table. azlin does not
compute or reformat it: it runs `az vm list-usage` for the region the active
context selects and prints that command's own table, filtered to the vCPU rows.

```
vCPU Quota:
Name                                    Current    Limit
--------------------------------------  ---------  -------
Total Regional vCPUs                    50         100
Standard DSv3 Family vCPUs              32         64
```

`Current` is what Azure counts as in use in that region — which includes
capacity azlin did not create — and `Limit` is the subscription's regional quota.
Remaining capacity is `Limit - Current`; azlin does not subtract it for you. The
lookup is per-region, so a VM in another region is not counted here.

## Understanding Tmux Display

The `Tmux` column lists the active tmux session *names* on each VM, comma-separated:

- **`main, debug`**: two sessions, listed by name. Every session collected is
  named in the cell; the column is sized to the widest entry, and it is truncated
  to fit only when the terminal is too narrow to hold it.
- **`-`**: the VM reported no sessions, or could not be probed. Check stderr to
  tell those apart.

At most 20 sessions are collected per VM. When a VM has more, the cell shows the
first 20 and the count not shown is reported on stderr —
`Warning: <vm> has more than 20 tmux sessions; N are not shown.` — rather than in
the cell.

**Use case:** Identify which VMs have active work sessions running.

### VMs Without a Public IP

A VM with no public IP is reached through Azure Bastion instead of direct SSH.
`azlin list` does this automatically — there is no flag. Whenever the listing
contains a running VM with no public IP, azlin discovers the bastion hosts in
that VM's resource group and region, opens a tunnel, and probes through it.
The `Tmux`, `Agent`/`CPU%`/`Mem%`/`Disk%` and `Procs` columns are filled the same
way they are for a public VM.

**One tunnel per VM.** A Bastion tunnel is opened against a single VM's ARM
resource id and forwards to that VM alone. Tunnels to different VMs behind the
same bastion are not interchangeable, so `azlin list` opens one per VM:

```
Region westus2, bastion `bastion-westus2`, three VMs with no public IP:

  dev-vm-002  ──▶ 127.0.0.1:52341  ──▶ /subscriptions/…/dev-vm-002
  dev-vm-004  ──▶ 127.0.0.1:52342  ──▶ /subscriptions/…/dev-vm-004
  dev-vm-007  ──▶ 127.0.0.1:52343  ──▶ /subscriptions/…/dev-vm-007
```

Before `v2.6.126-rust.12ccf60` a single tunnel was shared across every VM behind
a bastion, so all the probes landed on whichever VM's tunnel was created first
and the rest reported no sessions.

**Discovery spans every listed resource group.** For *routing*, bastions are
looked up once per distinct resource group that actually contains a running VM
with no public IP — a listing where every VM has a public IP needs no routing
lookup. Table output also prints an `Azure Bastion Hosts` table, which is built
from every resource group in the listing whether or not anything there needs a
tunnel: it documents the bastions in the scope you asked about. So a listing of
public-IP-only VMs still issues one `az network bastion list` per resource group
for the table.

The two are not additive. The groups routing needs are a subset of the groups
the table covers, so the table's answers are reused and routing issues no
further calls — a table listing costs one lookup per resource group whatever
enrichment flags are on. `-o json` and `-o csv` print no such table, so they pay
only for the groups that need routing, and nothing at all under `--no-tmux` with
no other enrichment flag.

The table is scoped to the *listing*, not to the subscription: the filters run
first, so unless you pass `--show-all-vms` a resource group whose VMs are all
deallocated contributes no VM to the listing, and therefore no lookup and no
bastions in the table.

If you lack `Microsoft.Network/bastionHosts/read` on one resource group, only
that resource group's private VMs lose their enrichment columns, and the group
is named on stderr rather than silently omitted from the table. The refusal is
reported once and reused, not re-attempted for routing.

**A tunnel that cannot be opened is reported.** Failure prints a warning on
stderr and the listing continues:

```
Warning: could not open a bastion tunnel to dev-vm-002 via bastion-westus2 (Bastion host 'bastion-westus2' not found in resource group 'dev-rg'); its sessions will not be listed.
```

The warning names the VM and the bastion, and carries the first line of the
error; use `-v` for the full chain. It goes to stderr, so `-o json` and `-o csv`
piped to a file are unaffected.

**A failed tunnel falls back to the private IP.** When the bastion cannot carry
the command, azlin retries at the VM's private address, which is routable if you
are on a VPN or a peered network. So a warning does not always mean the columns
are empty — it means the tunnel failed, and the row that follows may still be
filled in by the fallback. Only a command that *reached* the VM and failed there
is reported as-is: retrying that at the private IP could reach a different host
and print its numbers under this VM's name.

**A `-` in an enrichment column is not always "nothing to report."** A tunnel
failure is warned about by default, but an ordinary SSH probe that times out or
is refused is not — a fleet legitimately contains hosts you cannot reach, and a
warning per host per listing would drown the ones that matter. Run
`azlin list --verbose` to see, per VM, whether the probe failed or the VM really
had nothing running.

**Several bastions in one region.** A resource group can hold more than one
virtual network and so more than one bastion in a region. The first one Azure
lists is used and the others are named on stderr; the choice does not vary
between runs. If the wrong one is picked, narrow the listing with `--rg`.

**Tunnel fan-out is capped.** One invocation opens a bounded number of tunnels.
If a listing has more bastion-only VMs than that, the remainder are skipped and
the count is printed on stderr, so a truncated listing never looks like a
complete one. Narrow the listing with `--rg` or `--tag` to bring a large fleet
under the cap.

## Limitations

- **Bastion and VM must share a resource group.** Discovery looks for bastions
  in the resource groups of the VMs being listed. A hub-and-spoke topology, where
  the bastion lives in a hub resource group and the VMs in spokes, is not
  resolved; those VMs' enrichment columns stay empty unless their private IP
  happens to be routable from your machine. Resolving it properly requires
  VNet-peering discovery, which azlin does not do.
- **Only one bastion per resource group and region is used.** When a resource
  group has several bastions in one region, azlin routes through the first one
  Azure lists and names the rest in a warning. It does not test each bastion to
  find which one can actually see the VM.
- **VMs with colliding names lose their enrichment columns.** Azure only
  guarantees VM name uniqueness within a resource group, and `--show-all-vms` and
  `--all-contexts` can list two VMs with the same name. Tmux, health, latency and
  process data are all keyed by name for display, so azlin omits those columns —
  `Latency` included — for every VM in a colliding set and prints a warning
  naming them, rather than attributing one VM's sessions to the other's row.
- **Listings spanning several subscriptions omit tmux, health and process
  data.** Those lookups are subscription-scoped; under `--all-contexts` across
  more than one subscription they are skipped and a note is printed, rather than
  attributed to the wrong subscription.
- **`--show-procs` fills the `Procs` column in table output only.** The data is
  collected in every output format, but neither `-o json` nor `-o csv` carries a
  process field. Scripts cannot read process data out of `azlin list`; use
  `azlin connect <vm> -- ps aux` for that.
- **Latency is never measured through a bastion tunnel.** `--with-latency`
  measures a TCP connect to a routable address, so a VM you can only reach
  through its bastion has no measurement. Timing the tunnel would measure the
  tunnel, not the host. A VM whose recorded address cannot be parsed likewise has
  no measurement. "No measurement" renders as `-` in the table, an empty field in
  CSV and `null` in JSON — the table's `-` is a table convention, not a value a
  parser will see.
- **`-o csv` quotes its free-form fields but does not defuse formulas.** The
  `Tmux` column joins session names with `;` rather than `,` so it reads as one
  field, and *every* free-form field on the row — session, `Tmux`, VM name, OS,
  address, region, SKU and the health agent status — is quoted per RFC 4180 when
  it contains a comma, a quote or a newline. The remaining columns carry no
  delimiter to quote: `Status` is an enum, the CPU, memory, latency and health
  figures are computed here, and `Storage` is one of a fixed set of verdicts.
  Remote text is sanitised on the way in — control characters, bidirectional
  overrides and zero-width characters are stripped by `sanitize_remote_text` —
  but sanitising is not escaping, and
  neither is an allowlist: `parse_session_name` is not on this path. What is
  *not* handled is spreadsheet formula injection: a value beginning with `=`,
  `+`, `-` or `@` is still evaluated on open. Quoting does not address it — a
  quoted `"=1+1"` is still evaluated by Excel and Google Sheets. If you are
  opening the file in a spreadsheet, import it as text rather than opening it
  directly, or prefix suspect values with `'`.

    Note that `-o json` is **not** a workaround for this: it does not apply
    `sanitize_remote_text`, so Azure-supplied names reach JSON as Azure holds
    them. `serde_json` escapes what JSON syntax requires — `0x00`–`0x1F`, `"`
    and `\` — but `U+007F`, the C1 range and `U+2028` are emitted raw, so a
    pipeline that prints a field to a terminal is printing unsanitised text.
    JSON is the right choice for a program that parses it, not for a
    spreadsheet.

## Performance Considerations

### Fast Operations
- `azlin list` (default resource group) - **Fast** (~1-2 seconds)
- `azlin list --rg my-rg` - **Fast** (~1-2 seconds)
- `azlin list --tag key=value` - **Fast** (client-side filter)

### Slow Operations
- `azlin list --show-all-vms` - **Slow** (~10-30 seconds)
  - Queries all resource groups across subscription
  - Use sparingly or cache results

- `azlin list --all-contexts` - **Slow** (~5-60 seconds)
  - Depends on number of configured contexts
  - Authenticates to each context separately

- Bastion lookups cost one `az network bastion list` per distinct resource
  group, and a listing pays for them once rather than once per consumer. Table
  output pays for every resource group in the listing, because that is what the
  `Azure Bastion Hosts` table documents, and routing then reuses those answers
  at no further cost — so enrichment flags add no lookups. `-o json` and
  `-o csv` draw no table, so they pay only for the resource groups that
  actually contain a bastion-only running VM, and nothing at all under
  `--no-tmux` with no other enrichment flag.
- Bastion-only VMs additionally cost one tunnel each. Tunnels are opened
  sequentially; the SSH probes that follow run concurrently. Use `--no-tmux` to
  skip the probes.

**Tip:** For frequently-used multi-RG queries, use tags instead:
```bash
# Instead of slow --show-all-vms
azlin list --show-all-vms --tag project=myapp

# Prefer fast tag-based org + context
azlin list --tag project=myapp --contexts "prod*"
```

## Tag-Based Filtering

Tags enable powerful organizational queries:

```bash
# Find all VMs for a project
azlin list --tag project=webapp

# Find all production VMs
azlin list --tag environment=production

# Find VMs by team
azlin list --tag team=backend

# Find VMs by cost center
azlin list --tag costcenter=engineering
```

**Best practice:** Establish a tagging strategy for your organization:
- `environment`: dev, staging, production
- `project`: Project identifier
- `team`: Team or department
- `owner`: Primary contact
- `costcenter`: Billing allocation

See [`azlin tag`](tag.md) for managing tags.

## Multi-Context Scenarios

Multi-context support enables querying across:
- Multiple Azure subscriptions
- Multiple tenants
- Different authentication profiles

**Setup:**
```bash
# Create contexts for each subscription
azlin context create prod-eastus --subscription <sub-id> --rg prod-rg
azlin context create prod-westus --subscription <sub-id> --rg prod-rg-west
azlin context create dev-eastus --subscription <sub-id> --rg dev-rg

# Query production VMs across regions
azlin list --contexts "prod-*"

# Query all VMs across all contexts
azlin list --all-contexts
```

See [`azlin context`](../context/index.md) for context management.

## Troubleshooting

### No VMs Listed

**Symptoms:** Empty table, or fewer VMs than you expected.

**Check the footer first.** `azlin list` reports what its filters removed, which
separates "the resource group is empty" from "everything was filtered out":

```
Total: 0 VMs | 0 running | 2 excluded by --vm-pattern | 4 hidden (stopped/deallocated)
```

| Footer clause | Fix |
|---------------|-----|
| `{n} excluded by --tag` | Drop or correct `--tag` |
| `{n} excluded by --vm-pattern` | Widen or drop `--vm-pattern` |
| `{n} hidden (stopped/deallocated)` | `azlin list --all` |
| No extra clause on the `Total:` line | Nothing was filtered — check the resource group and your login |

```bash
# Nothing was hidden, so verify where you are pointed
azlin list --rg <your-rg>
az account show

# Scan every resource group (still running-only; add --all for stopped VMs)
azlin list -a
azlin list -a --all
```

### Quota Section Is Empty

**Symptoms:** `-q` prints the `vCPU Quota:` heading and nothing under it, which
means the underlying `az vm list-usage` call failed or returned no vCPU rows for
the region. azlin does not currently distinguish the two — the failure is not
reported (tracked in #1145) — so run the command yourself to see the cause.

**Solutions:**
```bash
# Check Azure CLI authentication
az account show

# Verify subscription has access
az vm list-usage --location eastus --output table

# Try different region
azlin list --rg <rg>  # Omit -q to skip the quota lookup entirely
```

### Tmux Column Shows `-` But Sessions Exist

**Symptoms:** The `Tmux` column shows `-` for a running VM you know has tmux
sessions.

**First, check stderr.** A `-` with a warning means azlin could not probe the VM;
a `-` with no warning means the VM answered and had no sessions. The two look
identical in the table:

```bash
azlin list            # warnings and notes go to stderr
azlin -v list         # adds per-VM detail, including skipped VMs
```

**Possible causes:**

| What you see on stderr | Cause | What to do |
|------------------------|-------|------------|
| `Warning: could not open a bastion tunnel to <vm> via <bastion>` | The bastion is missing, RBAC denies it, or the tunnel timed out | Run `azlin -v list` for the full error; confirm the bastion exists in the VM's resource group |
| `Warning: ... VMs were skipped ...` from the tunnel cap | More bastion-only VMs than one invocation opens tunnels for | Narrow the listing with `--rg` or `--tag` |
| `Warning: VM name(s) ... appear in more than one resource group` | Two listed VMs share a name, so `Tmux`, health, `Latency` and `Procs` are withheld from both | List them one resource group at a time with `--rg` |
| `Warning: <vm> has more than 20 tmux sessions` | The per-VM session cap; the count not shown is named | Nothing to fix — the cell shows the first 20 |
| `Note: this listing spans N subscriptions` | Tmux, health and process data are subscription-scoped | Use `--contexts` to select one subscription at a time |
| `Note: this listing reads subscription X but probes would run against Y` | The one subscription read is not the one probes use, so the same columns are withheld — the gate is on subscription identity, not on how many were read | `az account set --subscription X`, or point the context at the subscription you are on |
| `Note: ... pins subscription X by name ...` | A context pinned its subscription by name, which cannot be matched against the id probes carry | Pin the context by subscription id |
| Nothing | The VM answered and reported no sessions, or tmux is not installed | Check on the VM directly |

**Check the VM directly:**
```bash
# Verify VM is reachable
azlin connect myvm -- echo "test"

# Check tmux manually
azlin connect myvm -- tmux ls

# Skip tmux display
azlin list --no-tmux
```

**If several VMs behind one bastion all report zero except one**, you are running
a build older than `v2.6.126-rust.12ccf60`, which shared a single tunnel across
every VM behind a bastion. Check and upgrade:

```bash
azlin --version
azlin update
```

**If a private VM in a non-default resource group reports zero under
`--show-all-vms`**, upgrade for the same reason: bastion discovery used to run
against one resource group only. See
[VMs Without a Public IP](#vms-without-a-public-ip).

### VM Names Truncated

**Symptoms:** Long VM names cut off with "..." in table output.

**Solution:**
```bash
# Use wide flag (NEW in v0.3.2)
azlin list --wide
azlin list -w
```

### Slow Performance

**Symptoms:** `azlin list` takes >10 seconds.

**Solutions:**
```bash
# Disable the tmux probes — the expensive part
azlin list --no-tmux

# Drop the quota footer too if you had asked for it with -q
azlin list --no-tmux

# If using --show-all-vms, try scoping to specific RG
azlin list --rg my-rg  # Much faster
```

### Context Pattern No Match

**Symptoms:** `azlin list --contexts "prod*"` returns no results.

**Solutions:**
```bash
# List configured contexts
azlin context list

# Verify pattern matches context names
azlin list --contexts "production-*"

# Try wildcard at both ends
azlin list --contexts "*prod*"
```

## Advanced Usage

### Scripting and Automation

```bash
# Get VM count
vm_count=$(azlin list --no-tmux | grep -c "Running")

# Check if specific VM exists
if azlin list | grep -q "myvm"; then
    echo "VM exists"
fi

# Export VM list (JSON is the parseable format; see Limitations)
azlin -o json list --wide --no-tmux > vms.json
```

### Monitoring Workflows

```bash
# Check quota before provisioning
azlin list -q  # Review "remaining" quota

# Verify new VM appears
azlin new --name test && azlin list

# Monitor multi-region deployment
azlin list --contexts "prod-*" --all
```

### Cost Tracking

```bash
# Find stopped VMs to deallocate
azlin list --all | grep "Stopped"

# Review large VMs for cost optimization
azlin list --wide | grep "E64"

# See per-team resource usage
azlin list --tag team=backend
azlin list --tag team=frontend
```

## Related Commands

- [`azlin new`](new.md) - Provision new VMs
- [`azlin connect`](connect.md) - Connect to VM by name
- [`azlin status`](status.md) - Detailed VM status
- [`azlin session`](session.md) - Manage session names
- [`azlin tag`](tag.md) - Manage VM tags
- [`azlin context list`](../context/list.md) - List configured contexts

## Source Code

`azlin list` is implemented in Rust; the Python modules this section used to
link to no longer exist.

- [cmd_list.rs](https://github.com/rysweet/azlin/blob/main/rust/crates/azlin/src/cmd_list.rs) - command entry point, flag handling and enrichment gating
- [cmd_list_data.rs](https://github.com/rysweet/azlin/blob/main/rust/crates/azlin/src/cmd_list_data.rs) - bastion discovery, tunnel planning, and the tmux/health/process/latency collectors
- [cmd_list_render.rs](https://github.com/rysweet/azlin/blob/main/rust/crates/azlin/src/cmd_list_render.rs) - table, JSON and CSV rendering
- [list_helpers.rs](https://github.com/rysweet/azlin/blob/main/rust/crates/azlin/src/list_helpers.rs) - bastion-host detection used by the `Azure Bastion Hosts` table
- [active_context.rs](https://github.com/rysweet/azlin/blob/main/rust/crates/azlin/src/active_context.rs) - multi-context and region resolution

## See Also

- [All VM commands](index.md)
- [Context Management](../context/index.md)
- [Tag Management](tag.md)
- [Native Bastion Tunnel](../../bastion/native-tunnel.md) - How VMs with no public IP are reached, and why each one needs its own tunnel
- [Filter Disclosure](../../vm-lifecycle/filter-disclosure.md) - How `azlin list` reports the VMs its filters hid, in table, JSON and CSV
