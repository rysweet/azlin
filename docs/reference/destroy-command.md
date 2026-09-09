# `azlin destroy` Command Reference

`azlin destroy` deletes either one virtual machine and its session resources or
an entire Azure resource group.

Updated: 2026-09-09

## Syntax

```text
azlin destroy <VM_NAME> [OPTIONS]
```

```bash
# Delete one VM and its session resources
azlin destroy synthetic-vm --resource-group synthetic-rg

# Delete the entire resource group
azlin destroy synthetic-vm --resource-group synthetic-rg --delete-rg
```

`VM_NAME` remains required when `--delete-rg` is used for command-line
compatibility. In that mode, the resource group is the deletion target and the
VM name is not deleted separately.

## Arguments and options

| Argument or option | Default | Description |
|---|---|---|
| `VM_NAME` | Required | VM or session name. Used as the deletion target unless `--delete-rg` is set. |
| `--resource-group <RG>`, `--rg <RG>` | Configured resource group | Resource group containing the target. |
| `--delete-rg` | `false` | Delete the entire resolved resource group and everything it contains instead of deleting one VM. |
| `--dry-run` | `false` | Describe the selected deletion without authenticating or changing Azure resources. |
| `--force` | `false` | Skip confirmation. This option does not change the deletion target, error handling, or dry-run behavior. |

No feature-specific configuration is required. Resource-group resolution is
unchanged: pass `--resource-group` or `--rg` to select a group explicitly;
otherwise, azlin uses its configured resource group.

## Target selection

The two deletion modes are mutually exclusive:

| Command | Azure operation |
|---|---|
| `azlin destroy synthetic-vm --resource-group synthetic-rg` | Delete only `synthetic-vm` and its owned session resources. The resource group remains. |
| `azlin destroy synthetic-vm --resource-group synthetic-rg --delete-rg` | Delete `synthetic-rg` and every resource it contains. The VM-only deletion path does not run. |

One live command selects exactly one deletion branch. Resource-group deletion
invokes one Azure group-delete operation; it does not first delete the named VM
and does not fall back to VM deletion if the group operation fails. The
VM-scoped branch retains its existing teardown of the VM and owned session
resources.

## VM deletion

Without `--delete-rg`, `destroy` deletes the named VM and the resources owned by
that VM's azlin session:

1. Virtual machine
2. OS and data disks
3. Network interfaces
4. Public IP addresses owned by the session
5. Network security groups owned by the session and no longer in use

Shared, untagged, or still-attached resources remain. The resource group and
unrelated resources in it are not deleted.

Without `--force`, azlin uses the existing VM-specific confirmation. Declining
the prompt prints `Cancelled.` and performs no Azure deletion.

Progress and completion output identify the VM and its resource group. A
completion message is printed only after the deletion succeeds.

## Resource-group deletion

With `--delete-rg`, azlin deletes the resolved resource group through its Azure
CLI abstraction. The resulting Azure CLI operation is equivalent to:

```bash
az group delete --name synthetic-rg --yes
```

This removes every resource in the group, including resources that azlin did
not create, shared networking, storage, secrets, and other VMs.

Without `--force`, azlin asks:

```text
Delete resource group 'synthetic-rg' and all resources it contains?
```

Declining prints `Cancelled.` and performs no Azure deletion. Accepting invokes
the resource-group operation once. Progress and completion messages identify
the resource group and distinguish this operation from VM deletion.

## Dry-run behavior

Dry-run resolves the resource-group name, prints the selected scope, and
returns successfully before Azure authentication, confirmation, manager
construction, or any destructive operation.

### Preview one VM

```bash
azlin destroy synthetic-vm \
  --resource-group synthetic-rg \
  --dry-run
```

```text
Dry run: would delete VM 'synthetic-vm' and its owned session resources from resource group 'synthetic-rg'; the resource group and unrelated resources would remain.
```

### Preview an entire resource group

```bash
azlin destroy synthetic-vm \
  --resource-group synthetic-rg \
  --delete-rg \
  --dry-run
```

```text
Dry run: would delete resource group 'synthetic-rg' and all resources it contains.
```

`--force` is unnecessary in either dry-run command and does not make dry-run
destructive.

## Non-interactive use

Use `--force` only after verifying the target with `--dry-run`:

```bash
azlin destroy synthetic-vm \
  --resource-group synthetic-rg \
  --delete-rg \
  --dry-run

azlin destroy synthetic-vm \
  --resource-group synthetic-rg \
  --delete-rg \
  --force
```

The second command skips confirmation but retains the same whole-group target
and failure behavior.

## Errors and exit status

Azure failures produce a non-zero command exit and include the operation and
target in the error chain.

Representative VM failure:

```text
Error: failed to delete VM 'synthetic-vm' in resource group 'synthetic-rg'
```

Representative resource-group failure:

```text
Error: failed to delete resource group 'synthetic-rg'
```

Underlying Azure CLI details remain available in the error chain. azlin does
not print a completion message after a failed operation, convert the failure to
a warning, or try the other deletion mode.

## Related documentation

- [Safely Delete an Azure Resource Group](../how-to/destroy-resource-group.md)
- [Destroy Handler and Azure API](destroy-api.md)
- [NAT Gateway Provisioning](nat-gateway-provisioning.md#teardown-interaction)
- [Quick Reference](../QUICK_REFERENCE.md)
