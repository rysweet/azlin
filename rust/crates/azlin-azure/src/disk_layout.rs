//! The data-disk layout contract, and the probe/repair primitives built on it.
//!
//! Issue #1131 left VMs with attached but unformatted disks: cloud-init's disk
//! block sat behind `apt-get install` under `set -euo pipefail`, so on a
//! bastion-only VM with no outbound route the script died before reaching it.
//! Detecting that condition afterwards and repairing it in place means encoding
//! "what a correctly provisioned VM looks like" a second and a third time — and
//! a detector that drifts from the generator reports *healthy* VMs as broken,
//! forever, and silently.
//!
//! So the layout lives here, once, and the cloud-init generator, `azlin disk
//! check` and `azlin disk repair` all read it from this module.
//!
//! The part that is most often misread: nothing is ever mounted directly on
//! `/home` or `/tmp`. The disk is mounted at a *backing* path and a *bind*
//! mount exposes one subdirectory of it. See
//! `docs-site/storage/data-disk-layout.md`.

use crate::cloud_init::DiskConfig;

// ---------------------------------------------------------------------------
// The layout
// ---------------------------------------------------------------------------

/// What the bind mount exposes, and where.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BindKind {
    /// `<backing>/<user>` is bound at `/home/<user>`.
    UserHome,
    /// `<backing>/tmp` is bound at `/tmp`.
    Tmp,
}

/// One data-disk role: its LUN, its filesystem label, and where it lands.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct DiskRole {
    /// Stable role name. Appears in probe output, JSON and section names.
    pub name: &'static str,
    /// Azure LUN. This is attach order, not a fixed number per role.
    pub lun: u32,
    /// ext4 label written by `mkfs`.
    pub fs_label: &'static str,
    /// Where the filesystem itself is mounted.
    pub backing: &'static str,
    /// What the bind mount exposes.
    pub bind_kind: BindKind,
}

const HOME_ROLE: DiskRole = DiskRole {
    name: "home",
    lun: 0,
    fs_label: "azlin-home",
    backing: "/mnt/home-data",
    bind_kind: BindKind::UserHome,
};

const TMP_ROLE: DiskRole = DiskRole {
    name: "tmp",
    lun: 0,
    fs_label: "azlin-tmp",
    backing: "/mnt/tmp-data",
    bind_kind: BindKind::Tmp,
};

/// The roles a VM with this disk configuration is expected to have.
///
/// LUNs are assigned in attach order, so `--no-home-disk --tmp-disk-size 64`
/// puts the tmp disk at LUN 0. A detector that hard-codes "tmp is LUN 1" calls
/// that VM broken.
pub fn roles(config: &DiskConfig) -> Vec<DiskRole> {
    let mut out = Vec::with_capacity(2);
    let mut next_lun = 0;
    if config.home_disk {
        out.push(DiskRole {
            lun: next_lun,
            ..HOME_ROLE
        });
        next_lun += 1;
    }
    if config.tmp_disk {
        out.push(DiskRole {
            lun: next_lun,
            ..TMP_ROLE
        });
    }
    out
}

/// The role with this name, at this LUN.
///
/// `azlin disk repair` receives a finding rather than a config, and has to get
/// back to the layout without re-deriving it.
fn role_by_name(name: &str, lun: u32) -> Option<DiskRole> {
    match name {
        "home" => Some(DiskRole { lun, ..HOME_ROLE }),
        "tmp" => Some(DiskRole { lun, ..TMP_ROLE }),
        _ => None,
    }
}

/// `(bind source, bind target)` for a role on a VM with this admin username.
///
/// The source is always a *subdirectory* of the backing mount. Binding the
/// backing mount itself would expose `lost+found` in the user's home.
pub fn bind_pair(role: &DiskRole, username: &str) -> (String, String) {
    match role.bind_kind {
        BindKind::UserHome => (
            format!("{}/{}", role.backing, username),
            format!("/home/{}", username),
        ),
        BindKind::Tmp => (format!("{}/tmp", role.backing), "/tmp".to_string()),
    }
}

/// The name `azlin new` gives the managed disk for one role.
///
/// The convention is the only thing that says which role a disk was created
/// for, so it has one spelling. Two independent copies of it — which is what
/// `azlin disk check` and the `Storage` column each grew — can drift apart
/// silently, and the failure they drift into is `NoDisks`: exit 0 and a `--`
/// cell for every VM in the fleet, which is precisely the false pass this whole
/// issue is about.
fn data_disk_name(vm_name: &str, role: &DiskRole) -> String {
    format!("{}_{}", vm_name, role.name)
}

/// Every backing mount azlin can create, whatever the disk configuration is.
///
/// The provisioning preamble reports on all of them unconditionally, including
/// on a VM with no data disks: "both absent" is the answer to "where did my
/// /home go". It needs the paths without a `DiskConfig` to derive them from,
/// and taking them from anywhere but here is how a generator and its detector
/// drift apart.
pub fn all_backing_paths() -> [&'static str; 2] {
    [HOME_ROLE.backing, TMP_ROLE.backing]
}

/// The Azure udev symlink for a LUN.
///
/// `/dev/sdb` is assigned in attach order and can mean a different disk after a
/// reboot; this path means the same disk every time.
pub fn lun_device_path(lun: u32) -> String {
    format!("/dev/disk/azure/scsi1/lun{}", lun)
}

// ---------------------------------------------------------------------------
// fstab
// ---------------------------------------------------------------------------

/// An fstab entry azlin writes.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum FstabSpec {
    /// An ext4 data disk, keyed by UUID. `uuid_expr` may be a shell expansion
    /// such as `$HOME_UUID`, because the UUID is only known on the VM.
    Ext4ByUuid { uuid_expr: String, target: String },
    /// A bind mount exposing one subdirectory of a backing mount.
    Bind { source: String, target: String },
}

/// Render an fstab line. The only producer of fstab lines in azlin.
///
/// The options are not a matter of taste. `mode=1777` is a **tmpfs** option:
/// ext4 rejects the mount outright, and combined with `nofail` the rejection is
/// silent — the boot succeeds and the mount point quietly stays on the OS disk.
/// That cost a manual repair a whole cycle to find. There is one function that
/// can get this wrong now, and there is a test on it.
///
/// `nofail` is deliberate in the other direction: a missing data disk must not
/// stop the VM from booting. A VM that will not come up is a worse failure than
/// a VM with one directory on the OS disk.
pub fn fstab_line(spec: &FstabSpec) -> String {
    match spec {
        FstabSpec::Ext4ByUuid { uuid_expr, target } => {
            format!("UUID={} {} ext4 defaults,nofail 0 2", uuid_expr, target)
        }
        // `nofail` on the bind for the same reason it is on the ext4 line, and
        // it matters *more* here. systemd's fstab generator gives a bind mount
        // a hard `RequiresMountsFor` on its source, so without `nofail` a data
        // disk that fails to attach takes `local-fs.target` down with it and
        // the VM boots to emergency mode with no SSH. A missing data disk must
        // cost a directory, never the machine.
        FstabSpec::Bind { source, target } => {
            format!("{} {} none bind,nofail 0 0", source, target)
        }
    }
}

// ---------------------------------------------------------------------------
// mkfs
// ---------------------------------------------------------------------------

/// A `mkfs.ext4` that refuses to run over an existing filesystem.
///
/// Shared by `azlin disk repair` and `azlin disk add --mount`, which both run
/// against live VMs where a filesystem found on a disk may hold data the caller
/// cannot see. Cloud-init deliberately does *not* use this: it formats disks
/// that its own `azlin new` invocation created blank ninety seconds earlier,
/// and a guard there would silently skip a disk a previous failed boot had
/// partially formatted.
///
/// `dev_var` is the name of a shell variable holding the device path, so the
/// caller decides how the device was resolved. `privilege` is prefixed to each
/// command (`"sudo "` for callers running over SSH as a non-root user).
///
/// `-F` is not a contradiction of the guard: `blkid` decides whether to format
/// at all, and `-F` only stops `mke2fs` from asking the *other* question — "the
/// device looks unusual, proceed?" — interactively. These scripts run over SSH
/// with stdin closed, so a prompt is not a safety net; it is a hang followed by
/// an unexplained non-zero exit.
pub fn blkid_guarded_mkfs(dev_var: &str, label: Option<&str>, privilege: &str) -> String {
    let label_arg = label.map(|l| format!("-L {} ", l)).unwrap_or_default();
    format!(
        "if {privilege}blkid \"${dev_var}\" >/dev/null 2>&1; then\n  \
           echo 'azlin: filesystem already present, not reformatting'\n\
         else\n  \
           echo 'azlin: formatting (no filesystem found)'\n  \
           {privilege}mkfs.ext4 -F {label_arg}\"${dev_var}\"\n\
         fi"
    )
}

// ---------------------------------------------------------------------------
// Stages and findings
// ---------------------------------------------------------------------------

/// How far provisioning got on one disk.
///
/// The stages are ordered and each implies every earlier one succeeded, which
/// is what lets repair compose "the steps below the current stage".
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub enum DiskStage {
    /// The LUN has no block device. The disk is not attached.
    Absent,
    /// Attached, no filesystem. `mkfs` never ran. This is the #1131 case.
    Raw,
    /// Has a filesystem, but the backing path is not mounted.
    Formatted,
    /// Backing path mounted, bind missing — the user-facing path is still the
    /// OS disk.
    BackingMounted,
    /// Backing mount and bind both in place.
    Healthy,
}

impl DiskStage {
    /// The wire/JSON spelling.
    pub fn as_str(&self) -> &'static str {
        match self {
            DiskStage::Absent => "absent",
            DiskStage::Raw => "raw",
            DiskStage::Formatted => "formatted",
            DiskStage::BackingMounted => "backing-mounted",
            DiskStage::Healthy => "healthy",
        }
    }
}

impl std::fmt::Display for DiskStage {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(self.as_str())
    }
}

/// What the probe found for one expected disk.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DiskFinding {
    pub role: String,
    pub lun: u32,
    /// The resolved kernel device, or `None` at stage `absent`.
    pub device: Option<String>,
    /// Raw byte count read from the device, or `None` when there is no device.
    pub size_bytes: Option<u64>,
    pub stage: DiskStage,
    /// One line of plain English for the operator.
    pub detail: String,
}

/// What the provisioning ledger says, when there is one.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ProvisioningInfo {
    /// `/var/lib/azlin/provisioning-complete` exists.
    pub complete: bool,
    /// `ok`, `degraded`, or `unknown` on a VM with no status file.
    pub status: String,
    /// Whether `/var/lib/azlin/provisioning.tsv` exists at all. VMs that
    /// predate the ledger are exactly the VMs most likely to be broken, so this
    /// is a first-class case and not a parse failure.
    pub ledger_present: bool,
    pub failed_sections: Vec<String>,
}

/// The overall verdict for one VM's storage.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum StorageStatus {
    /// Every expected disk is `healthy`.
    Ok,
    /// At least one expected disk is not `healthy`.
    Degraded,
    /// The VM has no azlin data disks. Not a verdict about anything.
    NoDisks,
    /// The probe did not run, or its output could not be understood. Never
    /// rendered as a pass.
    Unknown,
}

impl StorageStatus {
    pub fn as_str(&self) -> &'static str {
        match self {
            StorageStatus::Ok => "ok",
            StorageStatus::Degraded => "degraded",
            StorageStatus::NoDisks => "no-disks",
            StorageStatus::Unknown => "unknown",
        }
    }
}

impl std::fmt::Display for StorageStatus {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.write_str(self.as_str())
    }
}

/// Everything one probe run says about one VM.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct DiskReport {
    pub status: StorageStatus,
    pub disks: Vec<DiskFinding>,
    pub provisioning: Option<ProvisioningInfo>,
}

// ---------------------------------------------------------------------------
// Username validation
// ---------------------------------------------------------------------------

/// Usernames are interpolated into shell scripts that run as root on the VM.
///
/// The cloud-init generator silently falls back to `azureuser` for a bad name,
/// which is right for provisioning — a VM must still come up. Here it is wrong:
/// repairing `azureuser`'s home when the caller asked for someone else's would
/// bind the wrong directory over the wrong path. So this rejects instead.
fn checked_username(username: &str) -> Result<&str, String> {
    if username.is_empty() {
        return Err("username must not be empty".to_string());
    }
    if !username
        .chars()
        .all(|c| c.is_ascii_alphanumeric() || c == '-' || c == '_')
    {
        return Err(format!(
            "username {:?} is not alphanumeric/-/_ and cannot be interpolated \
             into a shell script safely",
            username
        ));
    }
    Ok(username)
}

// ---------------------------------------------------------------------------
// The probe
// ---------------------------------------------------------------------------

/// Which roles a VM has, from the names of the data disks Azure has attached,
/// paired with the LUN Azure reports for each.
///
/// Returns `Err` with an operator-readable reason when Azure's LUN assignment
/// disagrees with [`roles`]: the probe addresses disks by LUN, so probing that
/// VM would read the wrong disk and report a healthy one as `absent`. A false
/// `degraded` on a fleet-wide surface is worse than no answer, so that is an
/// unknown rather than a verdict.
pub fn config_from_attached_disks(
    vm_name: &str,
    attached: &[(String, u32)],
) -> Result<DiskConfig, String> {
    let has = |role: &DiskRole| {
        attached
            .iter()
            .find(|(name, _)| *name == data_disk_name(vm_name, role))
            .map(|(_, lun)| *lun)
    };
    let config = DiskConfig {
        home_disk: has(&HOME_ROLE).is_some(),
        tmp_disk: has(&TMP_ROLE).is_some(),
    };

    for role in roles(&config) {
        let actual = has(&role);
        if actual != Some(role.lun) {
            return Err(format!(
                "disk '{}' is attached at LUN {}, but azlin's layout puts the {} disk at \
                 LUN {}. Probing it would read the wrong disk, so no verdict is given.",
                data_disk_name(vm_name, &role),
                actual.map_or_else(|| "none".to_string(), |l| l.to_string()),
                role.name,
                role.lun
            ));
        }
    }
    Ok(config)
}

/// A read-only script that prints what a VM's data disks actually look like.
///
/// The same script feeds `azlin disk check`, `azlin health` and `azlin list
/// --with-health`, which run it against every VM in a resource group. A status
/// query that formats a disk as a side effect would be the worst possible bug
/// in this file, so this emits no `mkfs`, no `mount`, and no write of any kind
/// — and there is a test asserting exactly that, by forbidden substring.
///
/// It prints facts and has no opinion; [`parse_disk_probe`] decides the verdict.
pub fn build_disk_probe_script(config: &DiskConfig, username: &str) -> Result<String, String> {
    let user = checked_username(username)?;
    let mut s = String::with_capacity(2048);

    s.push_str(
        "#!/bin/sh\n\
         # azlin storage probe (read-only). See docs-site/storage/data-disk-layout.md\n\
         azlin_source_of() {\n  \
           if command -v findmnt >/dev/null 2>&1; then\n    \
             azlin_src=\"$(findmnt -rno SOURCE \"$1\" 2>/dev/null | head -1)\"\n    \
             if [ -n \"$azlin_src\" ]; then printf '%s\\n' \"$azlin_src\"; return 0; fi\n  \
           fi\n  \
           awk -v t=\"$1\" '$2==t {print $1; exit}' /proc/mounts 2>/dev/null\n\
         }\n",
    );

    // Unrolled per role rather than looped: one `azlin-disk` line per expected
    // disk is the wire format, and a loop would make the count depend on
    // runtime state rather than on the configuration the caller passed.
    for role in roles(config) {
        let (_, bind_target) = bind_pair(&role, user);
        let lun = role.lun;
        s.push_str(&format!(
            "\nD=\"$(readlink -f {device} 2>/dev/null)\"\n\
             SZ=\"\"; FS=\"\"; LB=\"\"; PT=\"\"\n\
             if [ -n \"$D\" ] && [ -b \"$D\" ]; then\n  \
               SZ=\"$(lsblk -bdno SIZE \"$D\" 2>/dev/null | head -1 | tr -d ' ')\"\n  \
               FS=\"$(lsblk -dno FSTYPE \"$D\" 2>/dev/null | head -1 | tr -d ' ')\"\n  \
               LB=\"$(lsblk -dno LABEL \"$D\" 2>/dev/null | head -1 | tr -d ' ')\"\n  \
               if [ -z \"$FS\" ]; then FS=\"$(sudo -n blkid -s TYPE -o value \"$D\" 2>/dev/null)\"; fi\n  \
               if [ -z \"$LB\" ]; then LB=\"$(sudo -n blkid -s LABEL -o value \"$D\" 2>/dev/null)\"; fi\n  \
               PT=\"$(lsblk -dno PTTYPE \"$D\" 2>/dev/null | head -1 | tr -d ' ')\"\n  \
               if [ -z \"$PT\" ]; then PT=\"$(sudo -n blkid -s PTTYPE -o value \"$D\" 2>/dev/null)\"; fi\n\
             else\n  \
               D=\"\"\n\
             fi\n\
             BK=no; BD=no\n\
             if [ -n \"$D\" ]; then\n  \
               case \"$(azlin_source_of {backing})\" in \"$D\") BK=yes ;; esac\n  \
               case \"$(azlin_source_of {bind_target})\" in \"$D\"*) BD=yes ;; esac\n\
             fi\n\
             echo \"azlin-disk lun={lun} role={role} dev=$D size=$SZ fstype=$FS label=$LB backing=$BK bind=$BD pttype=$PT\"\n",
            device = lun_device_path(lun),
            backing = role.backing,
            bind_target = bind_target,
            lun = lun,
            role = role.name,
        ));
    }

    s.push_str(
        "\nPC=no\n\
         if [ -f /var/lib/azlin/provisioning-complete ]; then PC=yes; fi\n\
         PS=unknown\n\
         if [ -f /var/lib/azlin/provisioning-status ]; then\n  \
           PS=\"$(head -1 /var/lib/azlin/provisioning-status 2>/dev/null | tr -d ' ')\"\n  \
           if [ -z \"$PS\" ]; then PS=unknown; fi\n\
         fi\n\
         PL=no; PF=\"\"\n\
         if [ -f /var/lib/azlin/provisioning.tsv ]; then\n  \
           PL=yes\n  \
           PF=\"$(awk -F'\\t' '$2==\"failed\"{printf \"%s%s\", sep, $1; sep=\",\"}' \
/var/lib/azlin/provisioning.tsv 2>/dev/null)\"\n\
         fi\n\
         echo \"azlin-provisioning complete=$PC status=$PS ledger=$PL failed=$PF\"\n",
    );

    Ok(s)
}

// ---------------------------------------------------------------------------
// The parser
// ---------------------------------------------------------------------------

fn field<'a>(line: &'a str, key: &str) -> Option<&'a str> {
    line.split_whitespace()
        .find_map(|tok| tok.strip_prefix(key))
        .map(str::trim)
}

fn nonempty(value: Option<&str>) -> Option<String> {
    match value {
        Some(v) if !v.is_empty() => Some(v.to_string()),
        _ => None,
    }
}

fn stage_detail(role: &DiskRole, stage: DiskStage, bind_target: &str) -> String {
    match stage {
        DiskStage::Absent => format!(
            "no block device at LUN {}; the disk is not attached to the VM",
            role.lun
        ),
        DiskStage::Raw => format!(
            "no filesystem on the device; {} is on the OS disk",
            bind_target
        ),
        DiskStage::Formatted => format!(
            "filesystem present but {} is not mounted; {} is on the OS disk",
            role.backing, bind_target
        ),
        DiskStage::BackingMounted => format!(
            "{} is mounted but the bind is missing; {} is still on the OS disk",
            role.backing, bind_target
        ),
        DiskStage::Healthy => format!("{} backed by {}", bind_target, role.backing),
    }
}

/// Turn probe output into a verdict.
///
/// Output this cannot make sense of yields [`StorageStatus::Unknown`] and never
/// a false `degraded`: an older image or a truncated SSH session must not send
/// an operator to repair a VM that is fine. Unknown *trailing fields* are
/// ignored on purpose — forward compatibility here is the difference between
/// "one stale client reports unknown" and "one stale client tells everyone
/// their VMs are broken".
pub fn parse_disk_probe(output: &str, config: &DiskConfig) -> DiskReport {
    let expected = roles(config);

    let unknown = |disks: Vec<DiskFinding>, provisioning: Option<ProvisioningInfo>| DiskReport {
        status: StorageStatus::Unknown,
        disks,
        provisioning,
    };

    // The provisioning line is the proof the probe ran to completion. Its
    // absence means truncated or unrelated output, not a healthy VM.
    let Some(prov_line) = output
        .lines()
        .find(|l| l.trim_start().starts_with("azlin-provisioning "))
    else {
        return unknown(Vec::new(), None);
    };

    let provisioning = ProvisioningInfo {
        complete: field(prov_line, "complete=") == Some("yes"),
        status: field(prov_line, "status=").unwrap_or("unknown").to_string(),
        ledger_present: field(prov_line, "ledger=") == Some("yes"),
        failed_sections: field(prov_line, "failed=")
            .unwrap_or("")
            .split(',')
            .map(str::trim)
            .filter(|s| !s.is_empty())
            .map(str::to_string)
            .collect(),
    };

    let disk_lines: Vec<&str> = output
        .lines()
        .filter(|l| l.trim_start().starts_with("azlin-disk "))
        .collect();

    if disk_lines.len() != expected.len() {
        return unknown(Vec::new(), Some(provisioning));
    }

    let mut disks = Vec::with_capacity(expected.len());
    for (line, role) in disk_lines.iter().zip(expected.iter()) {
        // A line for a LUN or role the caller does not expect means the probe
        // and this build disagree about the layout. That is an unknown, not a
        // verdict about the VM.
        if field(line, "lun=").and_then(|v| v.parse::<u32>().ok()) != Some(role.lun)
            || field(line, "role=") != Some(role.name)
        {
            return unknown(Vec::new(), Some(provisioning));
        }

        let device = nonempty(field(line, "dev="));
        let size_bytes = field(line, "size=").and_then(|v| v.parse::<u64>().ok());
        let fstype = nonempty(field(line, "fstype="));
        let backing = field(line, "backing=") == Some("yes");
        let bind = field(line, "bind=") == Some("yes");

        // A whole disk carrying a partition table reports no `fstype` — the
        // filesystem is inside a partition, one level down. Calling that `raw`
        // would put it below `formatted` and let a repair format it with no
        // `--force`, which is the one thing the stage ladder exists to prevent.
        // `formatted` is the honest classification: something is on it, and
        // this tool cannot see what.
        let partitioned = nonempty(field(line, "pttype=")).is_some();

        let stage = if device.is_none() {
            DiskStage::Absent
        } else if fstype.is_none() && !partitioned {
            DiskStage::Raw
        } else if !backing {
            DiskStage::Formatted
        } else if !bind {
            DiskStage::BackingMounted
        } else {
            DiskStage::Healthy
        };

        // The probe output does not carry the admin username, and this parser
        // must not invent one: `/home/<user>` is the honest rendering.
        let (_, bind_target) = bind_pair(role, "<user>");

        disks.push(DiskFinding {
            role: role.name.to_string(),
            lun: role.lun,
            // Size without a device would be a claim about a disk that is not
            // there; the two always travel together.
            size_bytes: if device.is_some() { size_bytes } else { None },
            device,
            stage,
            detail: stage_detail(role, stage, &bind_target),
        });
    }

    let status = if expected.is_empty() {
        StorageStatus::NoDisks
    } else if disks.iter().all(|d| d.stage == DiskStage::Healthy) {
        StorageStatus::Ok
    } else {
        StorageStatus::Degraded
    };

    DiskReport {
        status,
        disks,
        provisioning: Some(provisioning),
    }
}

// ---------------------------------------------------------------------------
// Repair
// ---------------------------------------------------------------------------

/// The script that brings one disk up to the layout, starting from the stage it
/// is actually at.
///
/// Idempotent by construction rather than by a pile of guards: a `healthy` disk
/// produces no script at all, and each earlier stage adds back exactly the steps
/// below it. Every command is `sudo`-prefixed because this runs over SSH as the
/// admin user.
///
/// Returns `Err` — rather than a script that would do something surprising —
/// for the two cases where there is no safe repair to emit:
///
/// * `absent`: the LUN has no device. That is an Azure attach problem, and a
///   filesystem repair here would `mkfs` an empty variable.
/// * `formatted` without `force`: there is a filesystem the repair cannot read,
///   because it is not mounted, and it may hold data.
pub fn build_disk_repair_script(
    finding: &DiskFinding,
    username: &str,
    force: bool,
) -> Result<String, String> {
    let user = checked_username(username)?;
    let role = role_by_name(&finding.role, finding.lun)
        .ok_or_else(|| format!("unknown disk role {:?}", finding.role))?;
    let (bind_src, bind_target) = bind_pair(&role, user);

    match finding.stage {
        DiskStage::Healthy => return Ok(String::new()),
        DiskStage::Absent => {
            return Err(format!(
                "LUN {} has no block device on the VM, so there is no filesystem to \
                 repair. Check that the {} disk is attached: \
                 `az vm show -d --name <vm> --query storageProfile.dataDisks`",
                finding.lun, role.name
            ))
        }
        DiskStage::Formatted if !force => {
            return Err(format!(
                "refusing to format the {role} disk at LUN {lun}: it already has a \
                 filesystem, which may hold data this repair cannot see because it is \
                 not mounted. Look at it before deciding — `--force` reformats, and \
                 that is not reversible:\n    \
                 sudo mkdir -p /mnt/inspect && sudo mount {device} /mnt/inspect && \
                 ls -la /mnt/inspect",
                role = role.name,
                lun = finding.lun,
                device = lun_device_path(finding.lun),
            ))
        }
        _ => {}
    }

    // `--force` unlocks exactly one thing: `mkfs` over the filesystem of a
    // `formatted` disk. It is a plan-wide flag, so scoping it here is what
    // stops `azlin disk repair --force` — issued for a `formatted` home disk —
    // from also emitting `mkfs` against a `backing-mounted` tmp disk that is
    // mounted and in use. Only `mke2fs`'s own refusal stood in the way of that.
    let needs_mkfs =
        finding.stage < DiskStage::Formatted || (force && finding.stage == DiskStage::Formatted);
    let needs_backing_mount = finding.stage < DiskStage::BackingMounted;
    let home = role.bind_kind == BindKind::UserHome;

    let mut s = String::with_capacity(2048);
    s.push_str("set -euo pipefail\n");
    s.push_str(&format!(
        "DEV=\"$(readlink -f {} 2>/dev/null || true)\"\n\
         if [ -z \"$DEV\" ] || [ ! -b \"$DEV\" ]; then\n  \
           echo \"azlin: LUN {} has no block device\" >&2\n  \
           exit 1\n\
         fi\n",
        lun_device_path(role.lun),
        role.lun,
    ));

    if needs_mkfs {
        if force && finding.stage == DiskStage::Formatted {
            // --force is the only route past the guard, and it has to actually
            // get past it, so this is the one unguarded mkfs on this path.
            s.push_str(&format!(
                "echo 'azlin: --force given; reformatting an existing filesystem'\n\
                 sudo mkfs.ext4 -F -L {} \"$DEV\"\n",
                role.fs_label
            ));
        } else {
            s.push_str(&blkid_guarded_mkfs("DEV", Some(role.fs_label), "sudo "));
            s.push('\n');
        }
    }

    if needs_backing_mount {
        s.push_str(&format!(
            "sudo mkdir -p {backing}\n\
             sudo mount \"$DEV\" {backing}\n\
             echo \"azlin: mounted $DEV on {backing}\"\n",
            backing = role.backing
        ));
    } else {
        s.push_str(&format!(
            "echo 'azlin: {backing} is already mounted'\n",
            backing = role.backing
        ));
    }

    s.push_str(&format!("sudo mkdir -p {}\n", bind_src));

    if home {
        // Whether to copy is decided on the VM, not from the stage, because
        // only the VM can see both sides.
        //
        // The rule is: copy only into an empty destination. That is exactly the
        // freshly-formatted case, and it is the *only* case where copying is
        // safe. A `backing-mounted` disk already holds the real home; rsyncing
        // the OS-disk directory over it would overwrite live files with stale
        // ones — and, because rsync has no `--delete` here, the entry counts
        // could then never match, so every subsequent repair aborted with
        // "nothing was moved" after having already moved something.
        //
        // `rsync` lives in `default_dev_packages()`, not in the base image, and
        // repair exists for VMs where the package install failed — so the tool
        // is chosen at runtime, and `cp -a` (= `-dR --preserve=all`) covers the
        // same xattr/ACL intent.
        s.push_str(&format!(
            "if [ -n \"$(sudo ls -A {src} 2>/dev/null)\" ]; then\n  \
               echo 'azlin: {src} already holds data; keeping it and not copying over it'\n\
             else\n  \
               if command -v rsync >/dev/null 2>&1; then\n    \
                 COPY_MODE='rsync -aAXH'\n    \
                 sudo rsync -aAXH {target}/ {src}/\n  \
               else\n    \
                 COPY_MODE='cp -a'\n    \
                 sudo cp -a {target}/. {src}/\n  \
               fi\n  \
               echo \"azlin: copied with $COPY_MODE\"\n  \
               SRC_N=\"$(sudo find {target} -mindepth 1 | wc -l)\"\n  \
               DST_N=\"$(sudo find {src} -mindepth 1 | wc -l)\"\n  \
               if [ \"$SRC_N\" != \"$DST_N\" ]; then\n    \
                 echo \"azlin: copy verification failed ($SRC_N != $DST_N); nothing was moved\" >&2\n    \
                 exit 1\n  \
               fi\n  \
               if command -v rsync >/dev/null 2>&1; then\n    \
                 if [ -n \"$(sudo rsync -n -aAXH --out-format='%n' {target}/ {src}/)\" ]; then\n      \
                   echo 'azlin: rsync dry run still reports differences; nothing was moved' >&2\n      \
                   exit 1\n    \
                 fi\n    \
                 echo \"azlin: verified $SRC_N entries, rsync dry run clean\"\n  \
               else\n    \
                 echo \"azlin: verified $SRC_N entries by count only (rsync absent)\"\n  \
               fi\n\
             fi\n",
            target = bind_target,
            src = bind_src,
        ));

        // The `.old` rename is only needed when there is something to preserve.
        //
        // Binding over an empty directory loses nothing, so the common re-run
        // after a partial repair does not need it — and must not take it, since
        // a stale `.old` from the earlier attempt holds the real data. When
        // there *is* something to preserve and `.old` is already taken, this
        // stops rather than shadowing a populated directory under the bind: two
        // copies with one name is not a state to invent silently.
        s.push_str(&format!(
            "AZLIN_MOVED=no\n\
             if [ -n \"$(sudo ls -A {target} 2>/dev/null)\" ]; then\n  \
               if [ -e {target}.old ]; then\n    \
                 echo 'azlin: {target}.old is left over from an earlier repair and \
{target} is not empty; move or remove {target}.old and re-run' >&2\n    \
                 exit 1\n  \
               fi\n  \
               sudo mv {target} {target}.old\n  \
               AZLIN_MOVED=yes\n  \
               sudo mkdir -p {target}\n\
             fi\n\
             if ! sudo mount --bind {src} {target} || ! mountpoint -q {target}; then\n  \
               if [ \"$AZLIN_MOVED\" = yes ] && sudo rmdir {target} 2>/dev/null; then\n    \
                 sudo mv {target}.old {target}\n    \
                 echo 'azlin: bind mount failed; the original directory was restored' >&2\n  \
               else\n    \
                 echo 'azlin: bind mount failed; nothing was moved' >&2\n  \
               fi\n  \
               exit 1\n\
             fi\n\
             sudo chown {user}:{user} {src}\n\
             if [ \"$AZLIN_MOVED\" = yes ]; then\n  \
               echo 'azlin: bound {src} onto {target}, original kept at {target}.old'\n\
             else\n  \
               echo 'azlin: bound {src} onto {target}'\n\
             fi\n",
            target = bind_target,
            src = bind_src,
            user = user,
        ));
    } else {
        // `/tmp` contents are disposable, so this copy is best-effort by design
        // — and the asymmetry with the home copy above should be visible rather
        // than accidental.
        s.push_str(&format!(
            "sudo chmod 1777 {src}\n\
             {{ if [ -n \"$(sudo ls -A {src} 2>/dev/null)\" ]; then :; \
elif command -v rsync >/dev/null 2>&1; then sudo rsync -aAXH {target}/ {src}/; \
else sudo cp -a {target}/. {src}/; fi ; }} || true\n\
             if ! sudo mount --bind {src} {target} || ! mountpoint -q {target}; then\n  \
               echo 'azlin: bind mount failed' >&2\n  \
               exit 1\n\
             fi\n\
             echo 'azlin: bound {src} onto {target}'\n",
            src = bind_src,
            target = bind_target,
        ));
    }

    // Persisted, then checked as far as it honestly can be.
    //
    // Note what `mount -a` does *not* prove here: both paths are already
    // mounted by the time it runs, so it skips them, and the `mountpoint`
    // tests below pass because of the manual mounts this script made — not
    // because of the fstab lines. `findmnt --verify` adds the check that does
    // mean something without a reboot: it resolves every entry's source and
    // target and reports the ones that would be unreachable at boot.
    //
    // The `mode=`-class mistake is prevented structurally instead: every fstab
    // line azlin writes comes from `fstab_line`, which takes no options
    // argument at all, so there is nowhere for a stray option to enter. A
    // reboot remains the only end-to-end proof, and the command says so.
    let ext4 = fstab_line(&FstabSpec::Ext4ByUuid {
        uuid_expr: "$FS_UUID".to_string(),
        target: role.backing.to_string(),
    });
    let bind = fstab_line(&FstabSpec::Bind {
        source: bind_src.clone(),
        target: bind_target.clone(),
    });
    s.push_str(&format!(
        "FS_UUID=\"$(sudo blkid -s UUID -o value \"$DEV\")\"\n\
         if [ -z \"$FS_UUID\" ]; then\n  \
           echo 'azlin: could not read the filesystem UUID; not writing /etc/fstab' >&2\n  \
           exit 1\n\
         fi\n\
         if ! grep -qs \"^UUID=$FS_UUID \" /etc/fstab; then\n  \
           echo \"{ext4}\" | sudo tee -a /etc/fstab >/dev/null\n\
         fi\n\
         if ! grep -qsF \"{bind}\" /etc/fstab; then\n  \
           echo \"{bind}\" | sudo tee -a /etc/fstab >/dev/null\n\
         fi\n\
         if ! sudo mount -a; then\n  \
           echo 'azlin: mount -a reported an error; checking what actually mounted' >&2\n\
         fi\n\
         if ! mountpoint -q {backing} || ! mountpoint -q {target}; then\n  \
           echo 'azlin: {backing} or {target} is no longer mounted after mount -a' >&2\n  \
           exit 1\n\
         fi\n\
         if command -v findmnt >/dev/null 2>&1; then\n  \
           if ! findmnt --verify --tab-file /etc/fstab >/dev/null 2>&1; then\n    \
             echo 'azlin: findmnt --verify reports a problem in /etc/fstab:' >&2\n    \
             findmnt --verify --tab-file /etc/fstab >&2 || true\n    \
             exit 1\n  \
           fi\n\
         fi\n\
         echo 'azlin: /etc/fstab entries written; verified as far as is possible \
without a reboot'\n\
         echo 'azlin: healthy'\n",
        ext4 = ext4,
        bind = bind,
        backing = role.backing,
        target = bind_target,
    ));

    Ok(s)
}
