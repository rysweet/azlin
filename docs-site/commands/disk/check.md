# azlin disk check

Report whether a VM's data disks are provisioned the way azlin intended. Read
only — it never formats, mounts, or writes anything on the VM.

## Usage

```bash
azlin disk check VM_NAME [OPTIONS]
```

## Arguments

- `VM_NAME` - VM name or session name (required)

## Options

| Option | Description |
|--------|-------------|
| `--resource-group, --rg TEXT` | Azure resource group (default: configured resource group) |
| `--json` | Emit machine-readable JSON instead of the table |
| `-h, --help` | Show help message |

## Exit codes

`azlin disk check` is meant to be usable in a script or a cron job, so the
verdict is in the exit status, not only in the text:

| Code | Meaning |
|------|---------|
| `0` | Every expected disk is `healthy`, or the VM has no azlin data disks |
| `1` | Degraded — at least one disk is not at the `healthy` stage |
| `2` | The check could not be completed (VM unreachable, probe output unparseable) |

Code `2` is never reported as healthy. An unreachable VM is an unknown VM, and
this command will not answer a question it could not ask.

`1` is also azlin's generic failure status, and `clap` exits `2` on a usage
error, so the codes alone cannot tell "this VM is degraded" apart from "the
command did not run". A script that needs the difference should read `--json`
and branch on `status`, which is only ever emitted by a check that completed.

## Examples

### A correctly provisioned VM

```bash
azlin disk check build-vm
```

**Output:**
```
VM: build-vm  (rg: azlin-rg)
Storage: ok

  ROLE  LUN  DEVICE      SIZE     STAGE
  home  0    /dev/sdb    100G     healthy
  tmp   1    /dev/sdc    64G      healthy

Provisioning: complete, status=ok
```

Exit code `0`.

### A VM whose disks were never set up

This is the shape of issue #1131: both disks attached, neither formatted,
everything running on the 30 GB OS disk.

```bash
azlin disk check dev
```

**Output:**
```
VM: dev  (rg: rysweet-linux-vm-pool)
Storage: degraded

  ROLE  LUN  DEVICE      SIZE     STAGE
  home  0    /dev/sdb    1000G    raw
        no filesystem on the device; /home/<user> is on the OS disk
  tmp   1    /dev/sdc    200G     raw
        no filesystem on the device; /tmp is on the OS disk

Provisioning: complete, status unknown (no ledger — VM predates it)

Repair in place with:  azlin disk repair dev
```

Exit code `1`.

The stage is decided from what is on the VM right now — the LUN symlinks,
`blkid`, and the mount table — not from the provisioning ledger. VMs created
before the ledger existed have no ledger, and they are exactly the VMs most
likely to be broken. When a ledger *is* present it is reported as corroborating
detail, and the failed section names are listed:

```
Provisioning: complete, status=degraded
  failed sections: apt-update, apt-install
```

### Checking every VM in a resource group

```bash
for vm in $(azlin -o csv list | tail -n +2 | cut -d, -f1); do
  azlin disk check "$vm" >/dev/null 2>&1 || echo "$vm: storage degraded"
done
```

**Output:**
```
dev: storage degraded
deva2: storage degraded
deva3: storage degraded
```

### JSON output

```bash
azlin disk check dev --json
```

**Output:**
```json
{
  "vm": "dev",
  "resource_group": "rysweet-linux-vm-pool",
  "status": "degraded",
  "disks": [
    {
      "role": "home",
      "lun": 0,
      "device": "/dev/sdb",
      "size_gb": 1000,
      "stage": "raw",
      "detail": "no filesystem on the device; /home/<user> is on the OS disk"
    },
    {
      "role": "tmp",
      "lun": 1,
      "device": "/dev/sdc",
      "size_gb": 200,
      "stage": "raw",
      "detail": "no filesystem on the device; /tmp is on the OS disk"
    }
  ],
  "provisioning": {
    "complete": true,
    "status": "unknown",
    "ledger_present": false,
    "failed_sections": []
  }
}
```

`status` is one of `ok`, `degraded`, `no-disks`, or `unknown`. `stage` is one of
`absent`, `raw`, `formatted`, `backing-mounted`, `healthy` — see
[Provisioning stages](../../storage/data-disk-layout.md#provisioning-stages).

`detail` says `/home/<user>` literally rather than naming the account. The probe
output does not carry the admin username, and the parser that writes this field
does not invent one.

## How the check works

`azlin disk check` opens one SSH session (over Bastion if that is how the VM is
reached) and runs a read-only probe that prints facts, one line per expected
disk:

```
azlin-disk lun=0 role=home dev=/dev/sdb size=107374182400 fstype=ext4 label=azlin-home backing=yes bind=yes
azlin-disk lun=1 role=tmp dev=/dev/sdc size=68719476736 fstype= label= backing=no bind=no
azlin-provisioning complete=yes status=ok ledger=yes failed=
```

One `azlin-disk` line per expected disk, then exactly one `azlin-provisioning`
line:

- `dev` comes from `readlink -f /dev/disk/azure/scsi1/lunN`, never from
  `/dev/sd*` guessing. The LUN symlink is the stable identity — `/dev/sdb` can
  name a different disk after a reboot — which is why `lun` and `dev` are
  reported as separate fields and why the `DEVICE` column is only ever a
  resolved kernel name. To address the disk yourself, use the `lun`.
- `size` is the raw byte count from `lsblk -bdno SIZE` on that resolved device,
  rendered as the `SIZE` column and as `size_gb` in JSON. It is read from the
  device rather than from the Azure disk record deliberately: a disk that is
  attached in Azure but has no device on the VM is exactly the `absent` case,
  and the two sources would disagree there. A disk at stage `absent` has no
  device, so it has no size — `--` in the table, `null` in JSON.
- `fstype` and `label` come from `blkid`; empty means the disk is `raw`
- `backing` and `bind` come from `findmnt`, falling back to `/proc/mounts`
- the `azlin-provisioning` line reads `/var/lib/azlin/provisioning-complete`,
  `/var/lib/azlin/provisioning-status`, and the section names of any failed rows
  in `/var/lib/azlin/provisioning.tsv`. On a VM that predates the ledger the
  files are absent, so the probe emits `ledger=no status=unknown` — a
  first-class case, not a parse failure, and the common one for the fleet this
  command exists to fix.

azlin decides the verdict; the probe has no opinion. Output it cannot parse —
an older image, a truncated session — yields `unknown` and exit code `2`, never
a false `degraded`. A missing `azlin-provisioning` line is a parse failure; a
line reporting `ledger=no` is not.

The probe is cheap and read-only, which is why the same result also feeds
`azlin health` and `azlin list --with-health`.

## Storage in the health surfaces

The `Storage` column reports the same verdict without you having to ask per VM:

```bash
azlin list --with-health
```

**Output:**
```
SESSION   OS       Status    IP            Region    CPU  Mem   Agent  CPU%  Mem%  Disk%  Storage
dev       Ubuntu   running   10.0.1.4      westus2   8    32G   ok     12    41    98     degraded
build-vm  Ubuntu   running   10.0.1.7      westus2   8    32G   ok     4     22    31     ok
scratch   Ubuntu   running   10.0.1.9      westus2   4    16G   --     --    --    --     --
```

`--` means the probe did not run or could not be parsed — the same convention
the other health columns use. It is not a pass.

## Related

- [`azlin disk repair`](repair.md) - fix what this command reports
- [Data Disk Layout](../../storage/data-disk-layout.md) - what "as intended" means
- [Data disks are not mounted](../../troubleshooting/data-disks-not-mounted.md) - full diagnosis walkthrough
