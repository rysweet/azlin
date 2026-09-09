# Safely Delete an Azure Resource Group

Use `azlin destroy --delete-rg` when the entire resource group is disposable,
not merely one VM.

Updated: 2026-09-09

## Before you begin

Confirm that the group contains no resources you need. Whole-group deletion
removes all VMs, disks, networks, public IP addresses, NAT gateways, storage,
and other resources in the group, including resources that azlin did not
create.

Use synthetic or known disposable targets when rehearsing commands. Never use a
production resource group to test deletion behavior.

## Preview the deletion

Run a dry-run first:

```bash
azlin destroy synthetic-vm \
  --resource-group synthetic-rg \
  --delete-rg \
  --dry-run
```

The command exits successfully without Azure authentication or an Azure
deletion call:

```text
Dry run: would delete resource group 'synthetic-rg' and all resources it contains.
```

Check that the named resource group is the intended target. The positional VM
name is required by the command syntax but is not a separate deletion target
when `--delete-rg` is set.

## Delete with confirmation

Remove `--dry-run` and keep the confirmation prompt enabled:

```bash
azlin destroy synthetic-vm \
  --resource-group synthetic-rg \
  --delete-rg
```

azlin asks:

```text
Delete resource group 'synthetic-rg' and all resources it contains?
```

Answer `y` only if every contained resource can be deleted. Any other answer
cancels the command without invoking Azure deletion.

## Delete in automation

After validating the exact target with dry-run, use `--force` for a
non-interactive workflow:

```bash
azlin destroy synthetic-vm \
  --resource-group synthetic-rg \
  --delete-rg \
  --force
```

`--force` skips only the confirmation. It does not select resource-group
deletion by itself, suppress Azure errors, or weaken dry-run safety.

If Azure rejects or cannot complete the operation, azlin exits with an error
that identifies `synthetic-rg`. A successful completion message is not printed.
Fix the reported Azure error and rerun the same operation; azlin never falls
back to deleting only the VM.

## Delete only one VM instead

Omit `--delete-rg` when the resource group or any sibling resource must remain:

```bash
azlin destroy synthetic-vm \
  --resource-group synthetic-rg \
  --dry-run

azlin destroy synthetic-vm \
  --resource-group synthetic-rg
```

The preview states that `synthetic-vm` and its owned session resources would be
deleted while the group and unrelated resources remain. The live command uses
VM-specific confirmation and leaves the resource group intact.

For complete option and error semantics, see the
[`azlin destroy` command reference](../reference/destroy-command.md).
