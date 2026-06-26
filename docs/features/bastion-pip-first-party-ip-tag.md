# First-Party Usage IP Tag for Bastion Public IPs

Every Azure public IP that azlin creates for a bastion host is automatically
tagged with the Azure IP tag `FirstPartyUsage=/ATEVETNonProd`. This satisfies
the first-party usage tagging requirement for non-production Azure resources
with no extra steps from you.

## What is the First-Party Usage IP Tag?

Azure public IP addresses support **IP tags** — typed key/value metadata that
the platform recognizes for billing, compliance, and routing classification. IP
tags are distinct from ordinary Azure resource tags: they are applied at IP
allocation time via the `--ip-tags` argument of
`az network public-ip create` and use the form `<TagType>=<TagValue>`.

azlin now applies the following IP tag to every bastion public IP it creates:

| Field      | Value             |
| ---------- | ----------------- |
| Tag type   | `FirstPartyUsage` |
| Tag value  | `/ATEVETNonProd`  |

The resulting argument passed to the Azure CLI is:

```
--ip-tags FirstPartyUsage=/ATEVETNonProd
```

## Why Would I Use It?

This feature activates automatically. You don't need to opt in, pass a flag, or
change any configuration.

### Problem: Untagged Bastion Public IPs

First-party Azure subscriptions require non-production public IPs to carry the
`FirstPartyUsage` IP tag. Previously, bastion public IPs created by azlin had no
IP tag, so they failed compliance scans and had to be re-tagged manually after
the fact — a tedious, error-prone process that was easy to forget.

### Solution: Automatic Tagging at Creation

azlin now injects the required IP tag at allocation time, so every bastion
public IP is compliant the moment it is created. There is nothing to remember
and nothing to clean up afterward.

## Usage

The tag is applied transparently whenever azlin provisions bastion
infrastructure — for example, during the bastion pre-check auto-create flow or
any command that ensures bastion infrastructure exists:

```bash
azlin new --name my-vm --region eastus2 --size xl
# If bastion infrastructure is missing, azlin creates it, and the
# bastion public IP azlin-bastion-eastus2-pip is allocated with
# the FirstPartyUsage=/ATEVETNonProd IP tag.
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

## Verifying the Tag

You can confirm the IP tag on any bastion public IP with the Azure CLI:

```bash
az network public-ip show \
  --resource-group <rg> \
  --name azlin-bastion-eastus2-pip \
  --query ipTags \
  --output json
```

Expected output:

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
- **Idempotent**: The tag value is a fixed compile-time constant; repeated
  bastion provisioning always produces the same tag.
- **Non-destructive**: The tag is additive. All other public IP settings (SKU,
  allocation method, location, naming) are unchanged.
- **Does not retroactively modify** public IPs that were created before this
  feature. Only newly created bastion public IPs are tagged. Pre-existing IPs
  can be tagged manually if needed.

## Configuration Reference

There is no user-facing configuration for this feature. The IP tag type and
value are fixed:

| Setting   | Value                            | Configurable |
| --------- | -------------------------------- | ------------ |
| IP tag    | `FirstPartyUsage=/ATEVETNonProd` | No           |

The value is a non-sensitive compliance/billing identifier and is safe to appear
in command output and logs. It is passed as a discrete `argv` element (not a
shell string), so there is no command-injection surface.

## Related

- [Bastion Pre-Check for Private VMs](bastion-pre-check.md)
- [How to set up bastion infrastructure](../how-to/setup-bastion-infrastructure.md)
