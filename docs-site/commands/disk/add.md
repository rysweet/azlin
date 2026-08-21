# azlin disk add

Attach a new managed data disk to a VM, and optionally format and mount it in
one step.

## Usage

```bash
azlin disk add VM_NAME --size GB [OPTIONS]
```

## Arguments

- `VM_NAME` - VM name (required)

## Options

| Option | Description | Default |
|--------|-------------|---------|
| `--size INTEGER` | Disk size in GB (required) | — |
| `--sku TEXT` | Azure disk SKU (`Standard_LRS`, `StandardSSD_LRS`, `Premium_LRS`) | `Standard_LRS` |
| `--lun INTEGER` | Logical Unit Number to attach at | `0` |
| `--mount PATH` | Format (if needed) and mount the disk at `PATH`. Omit to attach without mounting | none |
| `--resource-group, --rg TEXT` | Azure resource group | configured resource group |
| `-h, --help` | Show help message | |

The disk is named `<vm-name>_datadisk_<lun>`.

## `--mount` is opt-in, and has no default

Attaching a disk and mounting it are separate asks. `--mount` once defaulted to
`/tmp`, which meant every `azlin disk add` would have formatted the new disk and
mounted it over the VM's `/tmp`. That default was removed (#1089): without
`--mount`, the disk is attached and left raw.

## Examples

### Attach without mounting

```bash
azlin disk add dev --size 500 --sku Premium_LRS --lun 2
```

**Output:**
```
Attached 500 GB disk 'dev_datadisk_2' to VM 'dev'
```

The disk is available at `/dev/disk/azure/scsi1/lun2` and has no filesystem.

### Attach, format, and mount

```bash
azlin disk add dev --size 500 --sku Premium_LRS --lun 2 --mount /data
```

**Output:**
```
Attached 500 GB disk 'dev_datadisk_2' to VM 'dev'
Mounted at /data (persisted in /etc/fstab)
```

The mount step:

1. waits up to 30 seconds for `/dev/disk/azure/scsi1/lun2` to appear
2. runs `blkid`; formats with `mkfs.ext4` **only if there is no filesystem**
3. mounts at `/data`
4. appends `UUID=<uuid> /data ext4 defaults,nofail 0 2` to `/etc/fstab`, if the
   UUID is not already there

Re-running the same command against an existing filesystem keeps it:

```
Attached 500 GB disk 'dev_datadisk_2' to VM 'dev'
  Existing filesystem kept (not reformatted)
Mounted at /data (persisted in /etc/fstab)
```

### When the mount fails

The disk exists and is billing whether or not the mount worked, and a failure
after the mount succeeded is a different problem from one before it. Both are
reported as such:

```
Error: Disk 'dev_datadisk_2' is attached to 'dev' and mounted at /data, but the
/etc/fstab entry could not be written: <detail>
The mount will NOT survive a reboot. Add it by hand, or re-run
`azlin disk add --lun 2 --mount /data` once the cause is fixed.
```

## This is not the `/home` and `/tmp` layout

`azlin disk add --mount` mounts the disk **directly** on the path you give it.
That is deliberately simpler than the bind-mount scheme cloud-init uses for the
`home` and `tmp` role disks, where the filesystem is mounted at `/mnt/home-data`
and a subdirectory is bind-mounted onto `/home/<user>`.

Consequences worth knowing:

- [`azlin disk check`](check.md) verifies the `home` and `tmp` role disks. Disks
  added with `azlin disk add` are outside its contract and are not reported.
- Do not point `--mount` at `/home/<user>` or `/tmp` on a VM that already has a
  role disk. Mounting over a bind target hides the disk underneath it without
  removing it, and both disks keep billing.

See [Data Disk Layout](../../storage/data-disk-layout.md) for the role-disk
scheme.

## Related

- [`azlin disk check`](check.md) - verify the `home` and `tmp` role disks
- [`azlin disk repair`](repair.md) - fix role disks that were never set up
- [`azlin new`](../vm/new.md) - `--home-disk-size`, `--tmp-disk-size`
