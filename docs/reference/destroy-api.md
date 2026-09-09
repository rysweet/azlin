# Destroy Handler and Azure API

This reference defines the internal Rust contracts used by `azlin destroy`.

Updated: 2026-09-09

## `DeleteTarget`

`DeleteTarget` represents the mutually exclusive target selected by the
lifecycle command:

```rust
pub enum DeleteTarget<'a> {
    VirtualMachine {
        resource_group: &'a str,
        vm_name: &'a str,
    },
    ResourceGroup {
        resource_group: &'a str,
    },
}
```

Construct `VirtualMachine` when `--delete-rg` is absent. Construct
`ResourceGroup` when `--delete-rg` is present. A single command constructs one
variant and invokes the handler once.

## `handle_delete`

```rust
pub fn handle_delete(
    ops: &dyn AzureOps,
    target: DeleteTarget<'_>,
) -> anyhow::Result<String>
```

The handler dispatches exactly one operation:

| Target | Operation | Error context |
|---|---|---|
| `DeleteTarget::VirtualMachine` | Existing VM teardown, including `AzureOps::delete_vm(resource_group, vm_name)` and owned session resources | VM name and resource group |
| `DeleteTarget::ResourceGroup` | `AzureOps::delete_resource_group(resource_group)` | Resource-group name |

The handler propagates failures. It does not retry, invoke both operations,
fall back to VM deletion, or return a success-shaped value after an error.

## `AzureOps::delete_resource_group`

The relevant `AzureOps` methods expose resource-group deletion alongside VM
deletion:

```rust
pub trait AzureOps {
    // Other Azure operations omitted.

    fn delete_vm(
        &self,
        resource_group: &str,
        name: &str,
    ) -> anyhow::Result<()>;

    fn delete_resource_group(
        &self,
        resource_group: &str,
    ) -> anyhow::Result<()>;
}
```

`VmManager` implements `delete_resource_group` through the established Azure
CLI wrapper. It passes these operation arguments:

```rust
["group", "delete", "--name", resource_group, "--yes"]
```

The wrapper remains responsible for timeout handling, argument sanitization,
and Azure or network error translation. Resource-group deletion uses a
dedicated 30-minute timeout because Azure waits for this long-running operation
to complete; ordinary operations retain the manager's configured timeout.
Lifecycle and handler code do not spawn a subprocess directly.

## Lifecycle ordering

`cmd_lifecycle` performs work in this order:

1. Resolve the resource-group name.
2. If `--dry-run` is set, print branch-specific output and return.
3. Confirm the selected target unless `--force` is set.
4. Authenticate and construct `VmManager`.
5. Construct one `DeleteTarget`.
6. Invoke `handle_delete` once.
7. Print target-specific completion output only after success.

Dry-run therefore does not authenticate, construct `VmManager`, confirm, call
`AzureOps`, or execute an Azure CLI operation.

## Contract invariants

- Default destruction runs teardown only for the named VM and its owned session
  resources.
- `--delete-rg` deletes only the named resource group.
- Each live invocation selects exactly one deletion branch.
- Resource-group deletion invokes exactly one Azure deletion operation.
- Declined confirmation invokes no Azure operation.
- `--force` affects confirmation only.
- VM and resource-group failures remain command failures.
- Failure output is contextual and suppresses completion output.

See the [`azlin destroy` command reference](destroy-command.md) for the public
CLI contract.
