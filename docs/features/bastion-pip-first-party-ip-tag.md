# Bastion Public IP IP-Tag (First-Party Usage)

Every Azure public IP that azlin creates for a bastion host is automatically
tagged with an Azure IP tag. The tag defaults to
`FirstPartyUsage=/ATEVETNonProd`, which satisfies the first-party usage tagging
requirement for non-production Azure resources with no extra steps from you.

Unlike earlier versions, the tag value is now **configurable**. You can override
it per-environment via a config file field, an environment variable, or the
`azlin config set` command — while the default keeps existing behavior
unchanged.

## What is the Bastion IP Tag?

Azure public IP addresses support **IP tags** — typed key/value metadata that
the platform recognizes for billing, compliance, and routing classification. IP
tags are distinct from ordinary Azure resource tags: they are applied at IP
allocation time via the `--ip-tags` argument of `az network public-ip create`
and use the form `<TagType>=<TagValue>`.

azlin applies the configured IP tag to every bastion public IP it creates.
With the default configuration, this is:

| Field      | Value             |
| ---------- | ----------------- |
| Tag type   | `FirstPartyUsage` |
| Tag value  | `/ATEVETNonProd`  |

The resulting argument passed to the Azure CLI is:

```
--ip-tags FirstPartyUsage=/ATEVETNonProd
```

## Why Would I Use It?

By default this feature activates automatically — you don't need to opt in for
the standard `FirstPartyUsage=/ATEVETNonProd` tag. Configuration is only needed
if your subscription or environment requires a **different** IP tag.

### Problem: Untagged or Wrongly-Tagged Bastion Public IPs

First-party Azure subscriptions require non-production public IPs to carry an
appropriate IP tag. Without one, bastion public IPs fail compliance scans and
have to be re-tagged manually after the fact — a tedious, error-prone process.
Different subscriptions or environments may also require a different tag value
than the non-production default.

### Solution: Configurable Tagging at Creation

azlin injects the required IP tag at allocation time, so every bastion public IP
is compliant the moment it is created. The tag value can be tailored to your
environment through configuration, and the default preserves backward
compatibility for existing users.

## Usage

The tag is applied transparently whenever azlin provisions bastion
infrastructure — for example, during the bastion pre-check auto-create flow or
any command that ensures bastion infrastructure exists:

```bash
azlin new --name my-vm --region eastus2 --size xl
# If bastion infrastructure is missing, azlin creates it, and the
# bastion public IP azlin-bastion-eastus2-pip is allocated with
# the configured IP tag (default: FirstPartyUsage=/ATEVETNonProd).
```

Under the hood, azlin runs the equivalent of:

```bash
az network public-ip create \
  --resource-group <rg> \
  --name azlin-bastion-eastus2-pip \
  --location eastus2 \
  --sku Standard \
  --allocation-method Static \
  --ip-tags FirstPartyUsage=/ATEVETNonProd \
  --output none
```

> The `--output none` flag suppresses the command's output, so running the
> command above prints nothing on success. To inspect the resulting IP tag, use
> the `show` query in [Verifying the Tag](#verifying-the-tag).

## Configuration

The IP tag value is controlled by the `bastion_pip_ip_tags` configuration
setting. It uses the standard `<TagType>=<TagValue>` IP-tag format expected by
`az network public-ip create --ip-tags`.

### Precedence

azlin resolves the effective IP tag in the following order (highest priority
first):

1. **Environment variable** `AZLIN_BASTION_PIP_IP_TAGS` — if set to a valid,
   non-empty value.
2. **Config file field** `bastion_pip_ip_tags` — if set to a valid, non-empty
   value.
3. **Built-in default** `FirstPartyUsage=/ATEVETNonProd`.

If the environment variable is set but invalid or empty, azlin logs a warning
and falls through to the config field, and then to the built-in default. This
guarantees a valid tag is always applied. The warning is emitted via `tracing`
to stderr, consistent with other azlin warnings, so look there if an expected
override does not take effect.

### Set via `azlin config set`

```bash
# Override the bastion public IP tag for all future bastion provisioning
azlin config set bastion_pip_ip_tags "FirstPartyUsage=/ATEVETProd"

# Inspect the persisted value
azlin config get bastion_pip_ip_tags
```

The value is validated at set time (see [Validation](#validation)).

> **Note:** `azlin config get` reports the **persisted** `bastion_pip_ip_tags`
> field only. The **effective** value used at provisioning time may differ: if
> `AZLIN_BASTION_PIP_IP_TAGS` is set it takes precedence, and if the field is
> unset the built-in default (`FirstPartyUsage=/ATEVETNonProd`) applies. See
> [Precedence](#precedence).

### Set via config file

The setting lives alongside other top-level fields in `~/.azlin/config.toml`
(or the directory named by `AZLIN_CONFIG_DIR`):

```toml
bastion_pip_ip_tags = "FirstPartyUsage=/ATEVETNonProd"
```

Config files that omit the field continue to work: the field defaults to
`FirstPartyUsage=/ATEVETNonProd`, so upgrades require no changes.

### Set via environment variable

```bash
# Overrides the config file for the current shell/session
export AZLIN_BASTION_PIP_IP_TAGS="FirstPartyUsage=/ATEVETProd"
azlin new --name my-vm --region eastus2
```

This is convenient for CI pipelines or one-off runs that target a different
subscription without editing the persisted config.

### Validation

When set via `azlin config set` (or read from the environment), the value is
validated against the IP-tag format:

- Must be in `Key=Value` form (contain an `=`).
- The key (tag type) must be non-empty.
- The value must not begin with `-` (prevents CLI flag injection).
- No control characters.
- Length must be at most 512 characters.

Invalid values are rejected by `azlin config set` with a descriptive error. An
invalid `AZLIN_BASTION_PIP_IP_TAGS` value is ignored (with a `tracing` warning on
stderr) in favor of the next source in the precedence order.

## Verifying the Tag

You can confirm the IP tag on any bastion public IP with the Azure CLI:

```bash
az network public-ip show \
  --resource-group <rg> \
  --name azlin-bastion-eastus2-pip \
  --query ipTags \
  --output json
```

Expected output (with the default tag):

```json
[
  {
    "ipTagType": "FirstPartyUsage",
    "tag": "/ATEVETNonProd"
  }
]
```

## Scope and Behavior

- **Applies to**: All bastion public IPs created by azlin going forward.
- **Configurable**: The tag value is resolved from environment, config, or the
  built-in default (see [Configuration](#configuration)).
- **Idempotent**: For a given configuration, repeated bastion provisioning
  always produces the same tag.
- **Non-destructive**: The tag is additive. All other public IP settings (SKU,
  allocation method, location, naming) are unchanged.
- **Does not retroactively modify** public IPs that were created before this
  feature, or public IPs created with a previous tag value. Only newly created
  bastion public IPs receive the currently configured tag. Pre-existing IPs can
  be re-tagged manually if needed.

## Configuration Reference

| Setting               | Config field / flag                         | Default                          | Configurable |
| --------------------- | ------------------------------------------- | -------------------------------- | ------------ |
| Bastion IP tag        | `bastion_pip_ip_tags`                       | `FirstPartyUsage=/ATEVETNonProd` | Yes          |
| Environment override  | `AZLIN_BASTION_PIP_IP_TAGS`                 | (unset)                          | Yes          |
| CLI command           | `azlin config set bastion_pip_ip_tags <v>`  | —                                | Yes          |

The value is a non-sensitive compliance/billing identifier and is safe to appear
in command output and logs. It is passed as a discrete `argv` element (not a
shell string), so there is no command-injection surface.

## Related

- [Bastion Pre-Check for Private VMs](bastion-pre-check.md)
- [How to set up bastion infrastructure](../how-to/setup-bastion-infrastructure.md)
