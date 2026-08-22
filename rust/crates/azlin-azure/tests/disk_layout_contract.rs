//! The data-disk layout contract, and the probe/repair primitives built on it.
//!
//! Issue #1131 left VMs with attached but unformatted disks. Detecting that
//! condition and repairing it in place means encoding "what a correctly
//! provisioned VM looks like" a second and third time — and a detector that
//! drifts from the generator reports *healthy* VMs as broken, forever, and
//! silently. So the layout lives in one place, `azlin_azure::disk_layout`, and
//! the generator, the detector and the repairer all read it from there.
//!
//! The trap this suite exists to prevent: nothing is ever mounted directly on
//! `/home` or `/tmp`. The disk is mounted at a backing path and a *bind* mount
//! exposes one subdirectory of it. A naive `findmnt /home` check reports every
//! correctly provisioned VM as broken. See
//! `docs-site/storage/data-disk-layout.md`.

use azlin_azure::cloud_init::DiskConfig;
use azlin_azure::disk_layout::{
    bind_pair, blkid_guarded_mkfs, build_disk_probe_script, build_disk_repair_script, fstab_line,
    parse_disk_probe, reformats_existing_filesystem, roles, DiskFinding, DiskStage, FstabSpec,
    StorageStatus,
};

const USER: &str = "azureuser";

fn both() -> DiskConfig {
    DiskConfig {
        home_disk: true,
        tmp_disk: true,
    }
}

fn home_only() -> DiskConfig {
    DiskConfig {
        home_disk: true,
        tmp_disk: false,
    }
}

fn tmp_only() -> DiskConfig {
    DiskConfig {
        home_disk: false,
        tmp_disk: true,
    }
}

fn finding(role: &str, lun: u32, stage: DiskStage) -> DiskFinding {
    DiskFinding {
        role: role.to_string(),
        lun,
        device: Some(format!("/dev/sd{}", (b'b' + lun as u8) as char)),
        size_bytes: Some(1_073_741_824_000),
        stage,
        detail: String::new(),
    }
}

// ---------------------------------------------------------------------------
// The layout itself
// ---------------------------------------------------------------------------

#[test]
fn home_takes_lun_zero_and_tmp_takes_lun_one() {
    let r = roles(&both());
    assert_eq!(r.len(), 2, "{r:?}");
    assert_eq!((r[0].name, r[0].lun), ("home", 0));
    assert_eq!((r[1].name, r[1].lun), ("tmp", 1));
    assert_eq!(r[0].fs_label, "azlin-home");
    assert_eq!(r[1].fs_label, "azlin-tmp");
    assert_eq!(r[0].backing, "/mnt/home-data");
    assert_eq!(r[1].backing, "/mnt/tmp-data");
}

/// LUN order is attach order. `--no-home-disk --tmp-disk-size 64` makes the tmp
/// disk the only data disk, and it takes LUN 0. A detector that hard-codes
/// "tmp is LUN 1" calls that VM broken.
#[test]
fn tmp_takes_lun_zero_when_there_is_no_home_disk() {
    let r = roles(&tmp_only());
    assert_eq!(r.len(), 1, "{r:?}");
    assert_eq!((r[0].name, r[0].lun), ("tmp", 0));
}

#[test]
fn a_vm_with_no_data_disks_has_no_roles() {
    assert!(roles(&DiskConfig::default()).is_empty());
}

/// The bind-mount scheme, stated as an assertion. This is the single most
/// commonly misread part of the layout.
#[test]
fn the_bind_exposes_a_subdirectory_of_the_backing_mount() {
    let r = roles(&both());

    let (src, dst) = bind_pair(&r[0], USER);
    assert_eq!(src, "/mnt/home-data/azureuser");
    assert_eq!(dst, "/home/azureuser");

    let (src, dst) = bind_pair(&r[1], USER);
    assert_eq!(src, "/mnt/tmp-data/tmp");
    assert_eq!(dst, "/tmp");
}

#[test]
fn the_bind_target_follows_the_configured_username() {
    let r = roles(&both());
    let (src, dst) = bind_pair(&r[0], "ryan");
    assert_eq!(src, "/mnt/home-data/ryan");
    assert_eq!(dst, "/home/ryan");
}

// ---------------------------------------------------------------------------
// One fstab producer — the `mode=1777` trap
// ---------------------------------------------------------------------------

/// `mode=1777` is a tmpfs option. ext4 rejects the mount, `nofail` makes the
/// rejection silent, and the mount point quietly stays on the OS disk. It cost
/// a manual repair a whole cycle to find. There is one function that can get
/// this wrong now, and this is the test on it.
#[test]
fn an_ext4_fstab_line_is_defaults_nofail_and_nothing_else() {
    let line = fstab_line(&FstabSpec::Ext4ByUuid {
        uuid_expr: "8f3c1a02-0000-0000-0000-000000000000".into(),
        target: "/mnt/home-data".into(),
    });
    assert_eq!(
        line,
        "UUID=8f3c1a02-0000-0000-0000-000000000000 /mnt/home-data ext4 defaults,nofail 0 2"
    );
    assert!(!line.contains("mode="), "{line}");
}

/// The bind line carries `nofail` for the same reason the ext4 line does, and
/// it matters more: systemd gives a bind mount a hard `RequiresMountsFor` on
/// its source, so a detached data disk would take `local-fs.target` down and
/// boot the VM into emergency mode with no SSH. A missing data disk must cost a
/// directory, never the machine.
#[test]
fn a_bind_fstab_line_cannot_wedge_the_boot() {
    let line = fstab_line(&FstabSpec::Bind {
        source: "/mnt/tmp-data/tmp".into(),
        target: "/tmp".into(),
    });
    assert_eq!(line, "/mnt/tmp-data/tmp /tmp none bind,nofail 0 0");
    assert!(!line.contains("mode="), "{line}");
}

/// Both kinds of entry, one property: nothing azlin writes to fstab may stop a
/// VM from booting.
#[test]
fn no_fstab_line_azlin_writes_can_block_boot() {
    for spec in [
        FstabSpec::Ext4ByUuid {
            uuid_expr: "$HOME_UUID".into(),
            target: "/mnt/home-data".into(),
        },
        FstabSpec::Bind {
            source: "/mnt/home-data/azureuser".into(),
            target: "/home/azureuser".into(),
        },
    ] {
        let line = fstab_line(&spec);
        assert!(line.contains("nofail"), "{line}");
    }
}

/// fstab by UUID, not by `/dev/sd*`: Azure reassigns those in attach order
/// across reboots, and persisting one is how a VM comes back with another
/// disk mounted where this one was.
#[test]
fn no_fstab_line_names_a_kernel_device() {
    for spec in [
        FstabSpec::Ext4ByUuid {
            uuid_expr: "$HOME_UUID".into(),
            target: "/mnt/home-data".into(),
        },
        FstabSpec::Bind {
            source: "/mnt/home-data/azureuser".into(),
            target: "/home/azureuser".into(),
        },
    ] {
        let line = fstab_line(&spec);
        assert!(!line.contains("/dev/sd"), "{line}");
    }
}

/// The guard that makes `azlin disk repair` and `azlin disk add --mount` safe
/// to point at a live VM. Shared, so there is one implementation to get right.
///
/// Built with the `"sudo "` prefix both callers pass: a zero-privilege variant
/// existed only so this test could omit the argument, which meant the test
/// covered a code path no VM ever ran.
#[test]
fn the_shared_mkfs_never_reformats_without_asking_blkid_first() {
    let script = blkid_guarded_mkfs("HOME_DEV", Some("azlin-home"), "sudo ");
    let mkfs_line = script
        .lines()
        .find(|l| l.contains("mkfs"))
        .unwrap_or_else(|| panic!("no format step:\n{script}"));
    let guard_at = script.find("blkid").unwrap_or_else(|| panic!("{script}"));
    let mkfs_at = script.find("mkfs").unwrap();
    assert!(
        guard_at < mkfs_at,
        "the blkid guard must precede the mkfs it guards:\n{script}"
    );
    assert!(mkfs_line.contains("-L azlin-home"), "{script}");
    // `-F` is not a hole in the guard: `blkid` decides *whether* to format, and
    // `-F` only stops `mke2fs` asking "the device looks unusual, proceed?" on a
    // stdin that is closed. Without it the format hangs, then exits non-zero
    // with no explanation.
    assert!(
        mkfs_line.contains("mkfs.ext4 -F"),
        "the format must not be able to stop for an interactive prompt over an \
         SSH session with no stdin:\n{script}"
    );
    assert!(
        script.contains("not reformatting"),
        "a skipped format must say so, or a no-op looks like a success:\n{script}"
    );

    // Position is not polarity. Swapping the guard's two branches — format when
    // `blkid` *succeeds* — keeps `blkid` before `mkfs`, keeps the label, and
    // keeps the "not reformatting" message, while doing exactly the opposite
    // thing: skipping the format on a blank disk and destroying a filesystem on
    // a populated one. So assert which branch the `mkfs` is in.
    let (then_branch, else_branch) = script
        .split_once("\nelse\n")
        .unwrap_or_else(|| panic!("the guard must have both branches:\n{script}"));
    assert!(
        !then_branch.contains("mkfs"),
        "the `blkid` success branch must not format — that is the branch where \
         a filesystem was found:\n{script}"
    );
    assert!(
        else_branch.contains("mkfs"),
        "the format belongs in the branch reached when `blkid` finds nothing:\n{script}"
    );
    assert!(
        then_branch.contains("not reformatting"),
        "the skip message belongs with the skip:\n{script}"
    );
}

// ---------------------------------------------------------------------------
// The probe
// ---------------------------------------------------------------------------

#[test]
fn the_probe_addresses_disks_by_lun_symlink_never_by_kernel_name() {
    let script = build_disk_probe_script(&both(), USER).expect("probe builds");
    assert!(script.contains("/dev/disk/azure/scsi1/lun0"), "{script}");
    assert!(script.contains("/dev/disk/azure/scsi1/lun1"), "{script}");
    assert!(
        !script.contains("/dev/sdb"),
        "`/dev/sdb` names a different disk after a reboot:\n{script}"
    );
}

/// The same probe feeds `azlin health` and `azlin list --with-health`, which
/// run against every VM in a resource group. A status query that formats a
/// disk as a side effect is the worst possible bug in this file.
#[test]
fn the_probe_is_read_only() {
    let script = build_disk_probe_script(&both(), USER).expect("probe builds");
    for forbidden in [
        "mkfs", "mount ", "umount", "rm ", "rm -", "dd ", "chmod", "chown", "tee ", "> /etc",
        ">> /etc", "fstab",
    ] {
        assert!(
            !script.contains(forbidden),
            "the probe must not contain {forbidden:?}:\n{script}"
        );
    }
}

#[test]
fn the_probe_emits_one_disk_line_per_role_and_exactly_one_provisioning_line() {
    let script = build_disk_probe_script(&both(), USER).expect("probe builds");
    assert_eq!(
        script.matches("azlin-disk ").count(),
        2,
        "one line per expected disk:\n{script}"
    );
    assert_eq!(
        script.matches("azlin-provisioning ").count(),
        1,
        "exactly one provisioning line:\n{script}"
    );
    for field in [
        "lun=", "role=", "dev=", "size=", "fstype=", "label=", "backing=", "bind=",
    ] {
        assert!(
            script.contains(field),
            "missing probe field {field:?}:\n{script}"
        );
    }
}

/// Size is read from the resolved device, not from the Azure disk record: a
/// disk attached in Azure with no device on the VM is exactly the `absent`
/// case, and the two sources disagree there.
#[test]
fn the_probe_reads_size_in_bytes_from_the_resolved_device() {
    let script = build_disk_probe_script(&both(), USER).expect("probe builds");
    assert!(
        script.contains("lsblk -bdno SIZE"),
        "size must be the raw byte count from the device:\n{script}"
    );
}

#[test]
fn the_probe_refuses_a_username_it_would_have_to_interpolate_unsafely() {
    assert!(build_disk_probe_script(&both(), "az; rm -rf /").is_err());
    assert!(build_disk_probe_script(&both(), "").is_err());
    assert!(build_disk_probe_script(&both(), "azureuser").is_ok());
}

/// `findmnt <mountpoint>` can print every layer at a stacked mountpoint. Taking
/// its first row reads the hidden tmpfs instead of the bind mounted over it.
/// `findmnt -T` asks the kernel-facing lookup for the one mount that currently
/// serves the path.
#[cfg(unix)]
#[test]
fn a_stacked_tmp_mount_uses_the_effective_data_disk_and_needs_no_repair() {
    use std::os::unix::fs::PermissionsExt;
    use std::process::Command;
    use std::time::{SystemTime, UNIX_EPOCH};

    let script = build_disk_probe_script(&tmp_only(), USER).expect("probe builds");
    let function_start = script.find("azlin_source_of() {").expect("source helper");
    let function_end = script[function_start..]
        .find("\n}\n")
        .map(|at| function_start + at + 3)
        .expect("source helper end");
    let helper = &script[function_start..function_end];

    let root = std::env::temp_dir().join(format!(
        "azlin-stacked-mount-{}-{}",
        std::process::id(),
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("system clock before unix epoch")
            .as_nanos()
    ));
    std::fs::create_dir_all(&root).expect("create scratch directory");
    let findmnt = root.join("findmnt");
    std::fs::write(
        &findmnt,
        r#"#!/bin/sh
case " $* " in
  *" -T /tmp "*) printf '%s\n' '/dev/sdc[/tmp]' ;;
  *" /tmp "*) printf '%s\n' 'tmpfs' '/dev/sdc[/tmp]' ;;
  *) printf '%s\n' '/dev/sdc' ;;
esac
"#,
    )
    .expect("write findmnt shim");
    let mut permissions = std::fs::metadata(&findmnt)
        .expect("findmnt metadata")
        .permissions();
    permissions.set_mode(0o755);
    std::fs::set_permissions(&findmnt, permissions).expect("chmod findmnt shim");

    let run = format!("{helper}\nazlin_source_of /tmp\n");
    let output = Command::new("sh")
        .arg("-c")
        .arg(run)
        .env("PATH", format!("{}:/usr/bin:/bin", root.display()))
        .output()
        .expect("run generated mount lookup");
    let source = String::from_utf8_lossy(&output.stdout).trim().to_string();
    let _ = std::fs::remove_dir_all(&root);

    assert!(output.status.success(), "{:?}", output.status);
    assert_eq!(
        source, "/dev/sdc[/tmp]",
        "the effective bind must win over the hidden tmpfs"
    );

    let transcript = format!(
        "azlin-disk lun=0 role=tmp dev=/dev/sdc size=214748364800 \
fstype=ext4 label=azlin-tmp backing=yes bind={}\n\
azlin-provisioning complete=yes status=ok ledger=yes failed=\n",
        if source.starts_with("/dev/sdc") {
            "yes"
        } else {
            "no"
        }
    );
    let report = parse_disk_probe(&transcript, &tmp_only());
    assert_eq!(report.status, StorageStatus::Ok, "{report:?}");
    assert_eq!(report.disks[0].stage, DiskStage::Healthy, "{report:?}");

    let repair = build_disk_repair_script(&report.disks[0], USER, false)
        .expect("an already healthy disk is not an error");
    assert!(
        repair.is_empty(),
        "repairing the effective healthy mount must execute no mount or fstab operation:\n{repair}"
    );
}

// ---------------------------------------------------------------------------
// The parser, against captured probe output
// ---------------------------------------------------------------------------
//
// These are the tests that close the drift gap: each transcript is what a real
// VM in that state prints, so a generator change that moves the layout without
// updating `roles()` breaks them.

const HEALTHY: &str = "\
azlin-disk lun=0 role=home dev=/dev/sdb size=1073741824000 fstype=ext4 label=azlin-home backing=yes bind=yes
azlin-disk lun=1 role=tmp dev=/dev/sdc size=214748364800 fstype=ext4 label=azlin-tmp backing=yes bind=yes
azlin-provisioning complete=yes status=ok ledger=yes failed=
";

/// The real `dev` VM, 2026-08-21: two Premium SSDs attached, neither ever
/// formatted, 1.2 TB billed and unused while the OS disk sat at 98%.
const DEV_VM_1131: &str = "\
azlin-disk lun=0 role=home dev=/dev/sdb size=1073741824000 fstype= label= backing=no bind=no
azlin-disk lun=1 role=tmp dev=/dev/sdc size=214748364800 fstype= label= backing=no bind=no
azlin-provisioning complete=yes status=unknown ledger=no failed=
";

#[test]
fn a_healthy_vm_parses_as_ok() {
    let report = parse_disk_probe(HEALTHY, &both());
    assert_eq!(report.status, StorageStatus::Ok, "{report:?}");
    assert_eq!(report.disks.len(), 2);
    assert!(report.disks.iter().all(|d| d.stage == DiskStage::Healthy));
    assert_eq!(report.disks[0].device.as_deref(), Some("/dev/sdb"));
    assert_eq!(report.disks[0].size_bytes, Some(1_073_741_824_000));
}

/// The #1131 evidence, as a test.
#[test]
fn the_dev_vm_transcript_parses_as_degraded_with_both_disks_raw() {
    let report = parse_disk_probe(DEV_VM_1131, &both());
    assert_eq!(report.status, StorageStatus::Degraded, "{report:?}");
    assert_eq!(
        report.disks.iter().map(|d| d.stage).collect::<Vec<_>>(),
        vec![DiskStage::Raw, DiskStage::Raw],
        "attached with no filesystem is `raw`, not `absent`: {report:?}"
    );
    assert!(
        report.disks.iter().all(|d| d.device.is_some()),
        "the devices exist; only the filesystems do not: {report:?}"
    );
}

/// A VM that predates the ledger has no ledger. Those are exactly the VMs this
/// command exists to fix, so `ledger=no` is a first-class case, not a parse
/// failure and not a reason to report `unknown` overall.
#[test]
fn a_missing_ledger_is_a_first_class_case_not_a_failure() {
    let report = parse_disk_probe(DEV_VM_1131, &both());
    let p = report
        .provisioning
        .expect("a provisioning line was present");
    assert!(p.complete);
    assert!(!p.ledger_present);
    assert_eq!(p.status, "unknown");
    assert!(p.failed_sections.is_empty());
    assert_eq!(
        report.status,
        StorageStatus::Degraded,
        "the verdict comes from the live disk state, not from the ledger"
    );
}

#[test]
fn failed_section_names_are_carried_through_from_the_ledger() {
    let transcript = format!(
        "{}azlin-provisioning complete=yes status=degraded ledger=yes failed=apt-update,apt-install\n",
        HEALTHY.lines().take(2).map(|l| format!("{l}\n")).collect::<String>()
    );
    let report = parse_disk_probe(&transcript, &both());
    let p = report.provisioning.expect("provisioning line");
    assert_eq!(p.failed_sections, vec!["apt-update", "apt-install"]);
    assert!(p.ledger_present);
}

/// `mkfs` ran, the mount did not. This disk can hold data, which is why repair
/// treats it differently from `raw`.
#[test]
fn a_formatted_but_unmounted_disk_is_formatted_not_raw() {
    let t = "\
azlin-disk lun=0 role=home dev=/dev/sdb size=1073741824000 fstype=ext4 label=azlin-home backing=no bind=no
azlin-provisioning complete=yes status=ok ledger=yes failed=
";
    let report = parse_disk_probe(
        t,
        &DiskConfig {
            home_disk: true,
            tmp_disk: false,
        },
    );
    assert_eq!(report.disks[0].stage, DiskStage::Formatted, "{report:?}");
    assert_eq!(report.status, StorageStatus::Degraded);
}

/// The backing mount is up and the bind is missing — `/home/<user>` is still
/// the OS disk. Reporting this as healthy is the mirror image of #1131 and
/// would hide exactly the same symptom.
#[test]
fn a_backing_mount_without_the_bind_is_not_healthy() {
    let t = "\
azlin-disk lun=0 role=home dev=/dev/sdb size=1073741824000 fstype=ext4 label=azlin-home backing=yes bind=no
azlin-provisioning complete=yes status=ok ledger=yes failed=
";
    let report = parse_disk_probe(
        t,
        &DiskConfig {
            home_disk: true,
            tmp_disk: false,
        },
    );
    assert_eq!(
        report.disks[0].stage,
        DiskStage::BackingMounted,
        "{report:?}"
    );
    assert_eq!(report.status, StorageStatus::Degraded);
}

#[test]
fn an_absent_lun_has_no_device_and_no_size() {
    let t = "\
azlin-disk lun=0 role=home dev= size= fstype= label= backing=no bind=no
azlin-provisioning complete=yes status=ok ledger=yes failed=
";
    let report = parse_disk_probe(
        t,
        &DiskConfig {
            home_disk: true,
            tmp_disk: false,
        },
    );
    assert_eq!(report.disks[0].stage, DiskStage::Absent);
    assert_eq!(report.disks[0].device, None);
    assert_eq!(report.disks[0].size_bytes, None);
}

/// Output the parser cannot make sense of yields `unknown` and never a false
/// `degraded`. An older image or a truncated session must not send an operator
/// to repair a VM that is fine.
#[test]
fn unparseable_output_is_unknown_never_degraded() {
    for garbage in [
        "",
        "   \n\n",
        "azlin-disk lun=0 role=home dev=/dev/sdb\n", // truncated mid-line, no provisioning line
        "Permission denied (publickey).\n",
        "azlin-disk lun=0 role=home dev=/dev/sdb size=1 fstype= label= backing=no bind=no\n", // no provisioning line
    ] {
        let report = parse_disk_probe(garbage, &both());
        assert_eq!(
            report.status,
            StorageStatus::Unknown,
            "input {garbage:?} must be unknown, not a verdict: {report:?}"
        );
    }
}

/// A probe run against a newer image may print fields this build does not know.
/// Forward compatibility here is the difference between "one stale client
/// reports unknown" and "one stale client tells everyone their VMs are broken".
#[test]
fn unknown_trailing_fields_do_not_break_the_parser() {
    let t = "\
azlin-disk lun=0 role=home dev=/dev/sdb size=1073741824000 fstype=ext4 label=azlin-home backing=yes bind=yes quota=off
azlin-disk lun=1 role=tmp dev=/dev/sdc size=214748364800 fstype=ext4 label=azlin-tmp backing=yes bind=yes quota=off
azlin-provisioning complete=yes status=ok ledger=yes failed= schema=2
";
    assert_eq!(parse_disk_probe(t, &both()).status, StorageStatus::Ok);
}

/// A VM with no data disks is not degraded and is not broken. It is a VM with
/// no data disks.
#[test]
fn a_vm_with_no_data_disks_is_no_disks_not_healthy_and_not_degraded() {
    let t = "azlin-provisioning complete=yes status=ok ledger=yes failed=\n";
    let report = parse_disk_probe(t, &DiskConfig::default());
    assert_eq!(report.status, StorageStatus::NoDisks, "{report:?}");
    assert!(report.disks.is_empty());
}

/// A disk line for a LUN the config does not expect means the probe and the
/// caller disagree about the layout. That is an unknown, not a verdict.
#[test]
fn a_disk_line_for_an_unexpected_lun_is_unknown() {
    let t = "\
azlin-disk lun=7 role=scratch dev=/dev/sdz size=1 fstype= label= backing=no bind=no
azlin-provisioning complete=yes status=ok ledger=yes failed=
";
    assert_eq!(parse_disk_probe(t, &both()).status, StorageStatus::Unknown);
}

// ---------------------------------------------------------------------------
// Stage ordering
// ---------------------------------------------------------------------------

/// The stages are ordered and each implies every earlier one. Repair composes
/// "the steps below the current stage", so this ordering is load-bearing rather
/// than documentation.
#[test]
fn the_stages_are_ordered() {
    assert!(DiskStage::Absent < DiskStage::Raw);
    assert!(DiskStage::Raw < DiskStage::Formatted);
    assert!(DiskStage::Formatted < DiskStage::BackingMounted);
    assert!(DiskStage::BackingMounted < DiskStage::Healthy);
}

// ---------------------------------------------------------------------------
// Repair composition
// ---------------------------------------------------------------------------

#[test]
fn repairing_a_raw_disk_formats_copies_verifies_binds_and_persists() {
    let script = build_disk_repair_script(&finding("home", 0, DiskStage::Raw), USER, false)
        .expect("raw is safe to repair without --force");

    let steps = [
        "mkfs",
        "/mnt/home-data",
        "/home/azureuser",
        "/etc/fstab",
        "mount -a",
    ];
    let mut last = 0usize;
    for step in steps {
        let at = script
            .find(step)
            .unwrap_or_else(|| panic!("repair omits {step:?}:\n{script}"));
        assert!(at >= last, "steps out of order at {step:?}:\n{script}");
        last = at;
    }
}

/// `raw` is the #1131 case: attached, never formatted, nothing to lose. Making
/// the common repair require a scary flag would push operators to `--force` by
/// habit, which is how the uncommon case gets destroyed.
#[test]
fn a_raw_disk_does_not_require_force() {
    assert!(build_disk_repair_script(&finding("home", 0, DiskStage::Raw), USER, false).is_ok());
}

/// A filesystem found on a live VM months later may hold data the repair cannot
/// see, because it is not mounted.
#[test]
fn repair_refuses_to_format_a_disk_that_already_has_a_filesystem() {
    let err = build_disk_repair_script(&finding("home", 0, DiskStage::Formatted), USER, false)
        .expect_err("a formatted disk must not be reformatted implicitly");
    assert!(
        err.contains("--force"),
        "the refusal must name the way through: {err}"
    );
}

#[test]
fn force_is_the_only_route_to_mkfs_over_an_existing_filesystem() {
    let script = build_disk_repair_script(&finding("home", 0, DiskStage::Formatted), USER, true)
        .expect("--force permits it");
    assert!(script.contains("mkfs"), "{script}");
}

/// The bind is missing; the filesystem is not. Nothing here may format.
#[test]
fn repairing_a_backing_mounted_disk_never_formats() {
    let script =
        build_disk_repair_script(&finding("home", 0, DiskStage::BackingMounted), USER, false)
            .expect("adding a missing bind needs no force");
    assert!(
        !script.contains("mkfs"),
        "the filesystem is already there:\n{script}"
    );
    assert!(script.contains("/home/azureuser"), "{script}");
    assert!(script.contains("/etc/fstab"), "{script}");
}

/// Running `azlin disk repair` twice must be safe, and the second run must do
/// nothing at all.
#[test]
fn repairing_a_healthy_disk_is_a_no_op() {
    use std::process::Command;

    let script = build_disk_repair_script(&finding("home", 0, DiskStage::Healthy), USER, false)
        .expect("healthy is not an error");
    assert!(
        script.trim().is_empty(),
        "a healthy disk must produce no script:\n{script}"
    );

    let output = Command::new("bash")
        .arg("-c")
        .arg(format!(
            "mount() {{ echo mount; }}\n\
             tee() {{ echo fstab-write; }}\n\
             {script}"
        ))
        .output()
        .expect("execute healthy repair plan");
    assert!(output.status.success(), "{:?}", output.status);
    assert!(
        output.stdout.is_empty(),
        "an already-healthy repair executed a mount or fstab operation:\n{}",
        String::from_utf8_lossy(&output.stdout)
    );
}

/// Execute a generated repair step and then model its authoritative re-probe as
/// degraded. Even on that failure path, the combined run cannot contain a
/// premature per-step `healthy` claim followed by the final degraded verdict.
#[cfg(unix)]
#[test]
fn repair_progress_cannot_contradict_a_degraded_final_reprobe() {
    let script =
        build_disk_repair_script(&finding("tmp", 1, DiskStage::BackingMounted), USER, false)
            .expect("repair plan");
    let harness = format!(
        "readlink() {{ printf '%s\\n' /dev/sdc; }}\n\
         sudo() {{\n  \
           case \"$1\" in\n    \
             blkid) printf '%s\\n' test-uuid ;;\n    \
             tee) cat >/dev/null ;;\n    \
             *) return 0 ;;\n  \
           esac\n\
         }}\n\
         mountpoint() {{ return 0; }}\n\
         findmnt() {{ return 0; }}\n\
         grep() {{ return 0; }}\n\
         {script}"
    )
    .replace(
        "if [ -z \"$DEV\" ] || [ ! -b \"$DEV\" ]; then",
        "if false; then",
    );
    let output = std::process::Command::new("bash")
        .arg("-c")
        .arg(harness)
        .output()
        .expect("execute repair step");
    assert!(
        output.status.success(),
        "repair harness failed: {}",
        String::from_utf8_lossy(&output.stderr)
    );

    let after = parse_disk_probe(
        "azlin-disk lun=0 role=tmp dev=/dev/sdc size=214748364800 \
         fstype=ext4 label=azlin-tmp backing=yes bind=no\n\
         azlin-provisioning complete=yes status=ok ledger=yes failed=\n",
        &tmp_only(),
    );
    assert_eq!(after.status, StorageStatus::Degraded);

    let transcript = format!(
        "{}\nStorage: {}\nError: still not fully repaired",
        String::from_utf8_lossy(&output.stdout),
        after.status
    );
    assert!(
        !transcript
            .lines()
            .any(|line| line.trim_end() == "azlin: healthy"),
        "one repair run emitted both healthy and not-repaired:\n{transcript}"
    );
    assert!(transcript.contains("Storage: degraded"), "{transcript}");
}

/// A missing LUN is an Azure attach problem. Emitting a filesystem repair for
/// it would run `mkfs` against an empty variable.
#[test]
fn an_absent_disk_is_not_a_filesystem_problem() {
    let err = build_disk_repair_script(&finding("home", 0, DiskStage::Absent), USER, false)
        .expect_err("absent must not produce a repair script");
    assert!(
        err.to_lowercase().contains("attach") || err.to_lowercase().contains("no device"),
        "the error should point at the attach, not the filesystem: {err}"
    );
}

/// The copy is the step that can lose data, so it is verified before the bind
/// is switched, and the original is retained until the verification passes.
#[test]
fn repair_verifies_the_copy_before_it_switches_the_bind() {
    let script =
        build_disk_repair_script(&finding("home", 0, DiskStage::Raw), USER, false).unwrap();

    let copy = script
        .find("/mnt/home-data/azureuser")
        .expect("a copy step");
    let verify = script
        .find("diff")
        .or_else(|| script.find("wc -l"))
        .unwrap_or_else(|| panic!("no verification step:\n{script}"));
    let bind = script
        .find("mount --bind")
        .unwrap_or_else(|| panic!("no bind step:\n{script}"));

    assert!(copy < verify, "copy then verify:\n{script}");
    assert!(verify < bind, "verify before switching the bind:\n{script}");
    assert!(
        script.contains(".old"),
        "the original must be retained until verification passes:\n{script}"
    );
}

/// Repair exists for VMs where the `apt-install` section failed, so it cannot
/// assume `rsync` is installed. `cp -a` is in coreutils.
#[test]
fn repair_copies_with_rsync_and_falls_back_to_cp() {
    let script =
        build_disk_repair_script(&finding("home", 0, DiskStage::Raw), USER, false).unwrap();
    assert!(script.contains("command -v rsync"), "{script}");
    assert!(script.contains("rsync -aAXH"), "{script}");
    assert!(script.contains("cp -a"), "{script}");
}

/// "Persisted to fstab" must never be reported for an entry that does not
/// actually mount. This is the check that catches a malformed option before the
/// next reboot does.
#[test]
fn repair_runs_mount_a_and_re_verifies_the_mount() {
    let script =
        build_disk_repair_script(&finding("home", 0, DiskStage::Raw), USER, false).unwrap();
    let fstab = script.find("/etc/fstab").expect("fstab step");
    let mount_a = script.find("mount -a").expect("mount -a");
    assert!(fstab < mount_a, "verify after writing:\n{script}");
    assert!(
        script[mount_a..].contains("findmnt") || script[mount_a..].contains("mountpoint"),
        "the mount table must be re-read after `mount -a`:\n{script}"
    );
}

/// Repair is the code most likely to reintroduce the `mode=1777` mistake — it
/// was written during the manual repair that made it.
#[test]
fn no_repair_script_writes_an_ext4_fstab_line_with_a_mode_option() {
    for (role, lun) in [("home", 0u32), ("tmp", 1u32)] {
        for stage in [DiskStage::Raw, DiskStage::BackingMounted] {
            let script = build_disk_repair_script(&finding(role, lun, stage), USER, false).unwrap();
            for line in script.lines().filter(|l| l.contains(" ext4 ")) {
                assert!(
                    !line.contains("mode="),
                    "{role}/{stage:?}: `mode=` on an ext4 line mounts nothing and \
                     says nothing: {line}"
                );
            }
        }
    }
}

#[test]
fn repair_sets_the_sticky_bit_on_the_backing_directory_not_on_tmp() {
    let script = build_disk_repair_script(&finding("tmp", 1, DiskStage::Raw), USER, false).unwrap();
    assert!(
        script.contains("chmod 1777 /mnt/tmp-data/tmp"),
        "chmodding /tmp alone is lost at the next boot:\n{script}"
    );
}

/// `--force` is a plan-wide flag, and it must not leak onto a disk whose stage
/// does not need `mkfs`.
///
/// `azlin disk repair vm --force` issued for a `formatted` home disk used to
/// emit `mkfs.ext4 -F` against a `backing-mounted` tmp disk in the same run —
/// a device that is mounted and in use. The only thing that stopped it
/// destroying the filesystem was `mke2fs` refusing to format a mounted device,
/// which is not a guarantee this code gets to rely on.
#[test]
fn force_does_not_reach_a_disk_whose_stage_needs_no_mkfs() {
    for stage in [DiskStage::BackingMounted, DiskStage::Healthy] {
        let script = build_disk_repair_script(&finding("tmp", 1, stage), USER, true)
            .unwrap_or_else(|e| panic!("{stage:?} with --force should not error: {e}"));
        assert!(
            !script.contains("mkfs"),
            "--force must only unlock `mkfs` for a `formatted` disk; {stage:?} \
             needs none:\n{script}"
        );
    }
}

/// The copy must never run over data this repair did not put there.
///
/// At stage `backing-mounted` the data disk may already hold the real home and
/// only the bind is missing. Copying `/home/<user>` — which at that point is
/// the empty mount point, or a stale OS-disk stub — over it would overwrite
/// live files with older ones. And because the copy has no `--delete`, the
/// entry counts could then never match, so every subsequent repair aborted
/// with "nothing was moved" *after* having already moved something.
#[test]
fn the_copy_is_skipped_when_the_destination_holds_data_from_elsewhere() {
    for stage in [DiskStage::Raw, DiskStage::BackingMounted] {
        let script = build_disk_repair_script(&finding("home", 0, stage), USER, false).unwrap();
        let guard = script
            .find("if [ -z \"$(sudo ls -A /mnt/home-data/azureuser 2>/dev/null)\" ]; then")
            .unwrap_or_else(|| panic!("no emptiness test before the copy:\n{script}"));
        let copy = script
            .find("rsync -aAXH /home/azureuser/")
            .unwrap_or_else(|| panic!("no copy step:\n{script}"));
        assert!(
            guard < copy,
            "{stage:?}: the copy must sit behind the guard, not beside it:\n{script}"
        );
        assert!(
            script.contains("already holds data this repair did not put there"),
            "{stage:?}: a skipped copy must say why:\n{script}"
        );
    }
}

/// An interrupted copy must be **resumed**, never mistaken for a finished one.
///
/// This is the path that binds a partial home over the real one. Interrupt a
/// `raw` repair during the copy — Ctrl-C, a dropped SSH session, a reboot — and
/// the VM is left with the disk formatted, the backing mounted, the bind never
/// made and `/mnt/home-data/<user>` half populated. The probe reads that as
/// `backing-mounted`, which is indistinguishable on the wire from a genuinely
/// provisioned disk whose bind was lost.
///
/// The old rule — "the destination is not empty, so do not copy" — then skipped
/// the copy *and with it the count check and the rsync dry run*, the two steps
/// that would have caught the shortfall, bound the partial directory over
/// `/home/<user>`, and told the operator to remove the original once they had
/// confirmed the new mount. If `.ssh/authorized_keys` was in the not-yet-copied
/// set they could not confirm anything: sshd reads `~` through the new bind.
///
/// So the copy records itself. Three states, three answers.
#[test]
fn an_interrupted_copy_is_resumed_rather_than_treated_as_complete() {
    let script =
        build_disk_repair_script(&finding("home", 0, DiskStage::BackingMounted), USER, false)
            .unwrap();

    let marker = script
        .find("COPY_STATE=/mnt/home-data/.azlin-copy-azureuser")
        .unwrap_or_else(|| panic!("no copy-state marker:\n{script}"));
    let in_progress = script
        .find("elif [ \"$COPY_WAS\" = in-progress ]; then")
        .unwrap_or_else(|| panic!("no resume branch:\n{script}"));
    let complete = script
        .find("elif [ \"$COPY_WAS\" = complete ]; then")
        .unwrap_or_else(|| panic!("no completed-copy branch:\n{script}"));

    assert!(marker < in_progress && in_progress < complete, "{script}");
    assert!(
        script[in_progress..complete].contains("COPY_DO=yes"),
        "an interrupted copy must be resumed, not skipped:\n{script}"
    );
    assert!(
        !script[complete..].starts_with("COPY_DO=yes"),
        "a verified copy must not be repeated:\n{script}"
    );
}

/// `in-progress` before the first byte, `complete` only after the verification.
///
/// Written the other way round the marker would say a copy finished that was
/// interrupted a moment later — which is precisely the claim it exists to stop
/// the repair from making.
#[test]
fn the_copy_marker_brackets_the_copy_and_its_verification() {
    let script =
        build_disk_repair_script(&finding("home", 0, DiskStage::Raw), USER, false).unwrap();

    let started = script
        .find("printf 'in-progress\\n' | sudo tee \"$COPY_STATE\"")
        .unwrap_or_else(|| panic!("the copy must record that it started:\n{script}"));
    let copy = script.find("sudo rsync -aAXH /home/azureuser/").unwrap();
    let verified = script.find("copy verification failed").unwrap();
    let finished = script
        .find("printf 'complete\\n' | sudo tee \"$COPY_STATE\"")
        .unwrap_or_else(|| panic!("the copy must record that it finished:\n{script}"));

    assert!(started < copy, "the marker goes down first:\n{script}");
    assert!(copy < verified, "{script}");
    assert!(
        verified < finished,
        "`complete` must come after the verification, not before it:\n{script}"
    );
}

/// The marker lives on the data disk but outside the bind source.
///
/// Inside it, it would appear in the user's home as a stray dotfile *and* it
/// would be one more entry on the destination side of the `SRC_N`/`DST_N` count
/// the copy is verified against — so every verified copy would fail its own
/// verification by exactly one.
#[test]
fn the_copy_marker_is_not_inside_the_users_home() {
    let script =
        build_disk_repair_script(&finding("home", 0, DiskStage::Raw), USER, false).unwrap();
    assert!(
        script.contains("COPY_STATE=/mnt/home-data/.azlin-copy-azureuser"),
        "{script}"
    );
    assert!(
        !script.contains("COPY_STATE=/mnt/home-data/azureuser/"),
        "the marker must not sit inside the directory whose entries are \
         counted:\n{script}"
    );
}

/// The window between the rename and a verified bind has a restore path.
///
/// Between `mv /home/<user> /home/<user>.old` and a `mount --bind` that took,
/// the user's home is a name that resolves to nothing. A dropped SSH session
/// delivers SIGHUP into exactly that window, and nothing said so afterwards.
#[test]
fn the_rename_is_covered_by_a_trap_until_the_bind_is_verified() {
    let script =
        build_disk_repair_script(&finding("home", 0, DiskStage::Raw), USER, false).unwrap();

    let trap = script
        .find("trap azlin_restore_target EXIT HUP INT TERM")
        .unwrap_or_else(|| panic!("no trap over the rename:\n{script}"));
    let rename = script
        .find("sudo mv /home/azureuser /home/azureuser.old")
        .unwrap();
    let bind = script
        .find("sudo mount --bind /mnt/home-data/azureuser /home/azureuser")
        .unwrap();
    let cleared = script
        .find("trap - EXIT HUP INT TERM")
        .unwrap_or_else(|| panic!("the trap must be cleared once the bind holds:\n{script}"));

    assert!(trap < rename, "the trap must precede the rename:\n{script}");
    assert!(rename < bind && bind < cleared, "{script}");
}

/// The bind target is recreated whether or not the rename happened.
///
/// `mkdir -p {target}` used to live inside the `AZLIN_MOVED` branch, so on the
/// path where the target was empty and never renamed — a resumed repair, or a
/// home that had already been moved aside — the bind ran against a directory
/// nobody had made.
#[test]
fn the_bind_target_exists_on_every_path_into_the_bind() {
    let script =
        build_disk_repair_script(&finding("home", 0, DiskStage::Raw), USER, false).unwrap();
    let mkdir = script
        .find("\nsudo mkdir -p /home/azureuser\n")
        .unwrap_or_else(|| panic!("the mkdir must be unconditional:\n{script}"));
    let bind = script
        .find("sudo mount --bind /mnt/home-data/azureuser /home/azureuser")
        .unwrap();
    assert!(mkdir < bind, "{script}");
}

/// Binding over an empty directory loses nothing, so the `.old` rename is only
/// taken when there is something to preserve — and never when `.old` is
/// already occupied by an earlier attempt's copy.
///
/// The old unconditional `[ ! -e .old ]` skip did the opposite: on a re-run
/// after a partial repair it left the populated directory in place and bound
/// over it, hiding the data under the mount while the message pointed the
/// operator at a stale `.old`.
#[test]
fn the_original_is_only_renamed_when_there_is_something_to_preserve() {
    let script =
        build_disk_repair_script(&finding("home", 0, DiskStage::Raw), USER, false).unwrap();
    assert!(
        script.contains("if [ -n \"$(sudo ls -A /home/azureuser 2>/dev/null)\" ]; then"),
        "the rename must be conditional on the target holding something:\n{script}"
    );
    assert!(
        script.contains("is left over from an earlier repair"),
        "a re-run that would need `.old` twice must stop, not shadow the \
         populated directory:\n{script}"
    );
    assert!(
        !script.contains("if [ ! -e /home/azureuser.old ]; then"),
        "the `.old`-exists skip silently bound over live data:\n{script}"
    );
}

/// A whole disk carrying a partition table has no `fstype` of its own — the
/// filesystem is one level down, inside a partition. Calling that `raw` puts it
/// below `formatted` and lets a repair format it with no `--force`.
#[test]
fn a_partitioned_disk_is_not_reported_as_blank() {
    let t = "\
azlin-disk lun=0 role=home dev=/dev/sdb size=1073741824000 fstype= label= backing=no bind=no pttype=gpt
azlin-provisioning complete=yes status=ok ledger=yes failed=
";
    let report = parse_disk_probe(
        t,
        &DiskConfig {
            home_disk: true,
            tmp_disk: false,
        },
    );
    assert_eq!(report.disks[0].stage, DiskStage::Formatted, "{report:?}");
    assert!(
        report.disks[0].stage >= DiskStage::Formatted,
        "a partitioned disk must require --force before any mkfs: {report:?}"
    );
}

/// Two identical findings must produce identical scripts. A repair that varies
/// run to run cannot be reviewed with `--dry-run`.
#[test]
fn repair_output_is_deterministic() {
    let f = finding("home", 0, DiskStage::Raw);
    assert_eq!(
        build_disk_repair_script(&f, USER, false).unwrap(),
        build_disk_repair_script(&f, USER, false).unwrap()
    );
}

#[test]
fn repair_refuses_a_username_it_would_have_to_interpolate_unsafely() {
    let f = finding("home", 0, DiskStage::Raw);
    assert!(build_disk_repair_script(&f, "az; rm -rf /", false).is_err());
    assert!(build_disk_repair_script(&f, "", false).is_err());
}

#[cfg(unix)]
#[test]
fn the_probe_and_repair_scripts_parse_as_shell() {
    use std::process::Command;

    let mut scripts = vec![build_disk_probe_script(&both(), USER).unwrap()];
    for stage in [DiskStage::Raw, DiskStage::BackingMounted] {
        scripts.push(build_disk_repair_script(&finding("home", 0, stage), USER, false).unwrap());
        scripts.push(build_disk_repair_script(&finding("tmp", 1, stage), USER, false).unwrap());
    }

    for script in scripts {
        let out = Command::new("bash")
            .arg("-n")
            .arg("-c")
            .arg(&script)
            .output()
            .expect("failed to run bash -n");
        assert!(
            out.status.success(),
            "bash -n rejected:\n{script}\n{}",
            String::from_utf8_lossy(&out.stderr)
        );
    }
}

// ---------------------------------------------------------------------------
// Failing closed
// ---------------------------------------------------------------------------

/// `blkid` failing is not the same statement as `blkid` finding nothing.
///
/// The guard used to be `if blkid …; then skip; else format; fi`, which formats
/// on *any* non-zero status — `blkid` missing from the image, `sudo` denied, an
/// I/O error on the device. Those are the same conditions under which the
/// caller's own filesystem detection is most likely to have misread the disk as
/// blank, so the "independent" guard was correlated with the thing it guarded.
/// `blkid` spells "nothing found" as exit 2, and only exit 2 is a licence to
/// format.
#[test]
fn the_blkid_guard_refuses_to_format_when_it_could_not_look() {
    let script = blkid_guarded_mkfs("DEV", Some("azlin-home"), "sudo ");
    assert!(
        script.contains("azlin_blkid_rc"),
        "the guard must look at the status, not merely at success:\n{script}"
    );
    assert!(
        script.contains("-ne 2"),
        "only `blkid`'s \"nothing found\" (exit 2) may lead to a format:\n{script}"
    );
    let refusal = script
        .find("refusing to format it")
        .unwrap_or_else(|| panic!("an undetermined disk must be refused:\n{script}"));
    let mkfs = script.find("mkfs.ext4").unwrap();
    assert!(refusal < mkfs, "{script}");
    assert!(
        script[refusal..mkfs].contains("exit 1"),
        "the refusal must stop the script, not fall through to the format:\n{script}"
    );
}

/// The same refusal reaches the repair script for every stage that formats.
#[test]
fn the_repair_inherits_the_fail_closed_guard() {
    let script =
        build_disk_repair_script(&finding("home", 0, DiskStage::Raw), USER, false).unwrap();
    assert!(script.contains("refusing to format it"), "{script}");
}

/// The probe says whether it could answer the filesystem question at all.
///
/// An empty `fstype=` meant two different things — "this disk is blank" and
/// "`lsblk` is missing and `sudo -n blkid` was denied" — and both read as
/// `raw`, the stage a repair formats without `--force`. Paired with a `blkid`
/// guard that also failed open, the two correlated failures reformatted a disk
/// nobody could read.
#[test]
fn an_unanswerable_filesystem_question_is_unknown_never_raw() {
    let out = "\
azlin-disk lun=0 role=home dev=/dev/sdb size=1 fstype= label= backing=no bind=no pttype= fsdet=no
azlin-provisioning complete=yes status=ok ledger=yes failed=
";
    let report = parse_disk_probe(out, &home_only());
    assert_eq!(
        report.status,
        StorageStatus::Unknown,
        "a probe that could not look must not report a blank disk: {report:?}"
    );

    // And the same line with the question answered is still `raw`.
    let answered = out.replace("fsdet=no", "fsdet=yes");
    let report = parse_disk_probe(&answered, &home_only());
    assert_eq!(report.status, StorageStatus::Degraded);
    assert_eq!(report.disks[0].stage, DiskStage::Raw);
}

/// A probe that predates `fsdet=` keeps its old reading.
///
/// Upgrading the client must not turn every VM in the fleet unknown; the field
/// has to be an explicit `no` to withhold the verdict.
#[test]
fn a_probe_without_the_field_is_read_as_before() {
    let out = "\
azlin-disk lun=0 role=home dev=/dev/sdb size=1 fstype= label= backing=no bind=no pttype=
azlin-provisioning complete=yes status=ok ledger=yes failed=
";
    let report = parse_disk_probe(out, &home_only());
    assert_eq!(report.status, StorageStatus::Degraded);
    assert_eq!(report.disks[0].stage, DiskStage::Raw);
}

/// The probe emits the field it is parsed against.
#[test]
fn the_probe_reports_whether_it_could_read_the_filesystem() {
    let script = build_disk_probe_script(&both(), USER).expect("probe builds");
    assert_eq!(
        script.matches("fsdet=$FSDET").count(),
        2,
        "one per disk line:\n{script}"
    );
    assert!(
        script.contains("FSDET=yes"),
        "something has to be able to set it:\n{script}"
    );
}

/// Nothing a VM says can move an operator's cursor.
///
/// The device path, the provisioning status and the failed-section names are
/// all read off the machine being diagnosed and printed into a table. They are
/// root-controlled on the VM, so this defends against no privilege boundary —
/// what it stops is one machine's output rewriting the rows of the machines
/// listed after it in a fleet sweep.
#[test]
fn remote_text_cannot_rewrite_the_report_around_it() {
    let out = "\
azlin-disk lun=0 role=home dev=/dev/sdb\u{1b}[2J size=1 fstype=ext4 label=azlin-home backing=yes bind=yes pttype= fsdet=yes
azlin-provisioning complete=yes status=deg\u{1b}[1;31mraded ledger=yes failed=setup-\u{7}rust
";
    let report = parse_disk_probe(out, &home_only());
    let provisioning = report.provisioning.expect("a provisioning line");
    assert_eq!(report.disks[0].device.as_deref(), Some("/dev/sdb[2J"));
    assert_eq!(provisioning.status, "deg[1;31mraded");
    assert_eq!(provisioning.failed_sections, vec!["setup-rust"]);
}

// ---------------------------------------------------------------------------
// --force is a permission, and the caller can ask what it permits
// ---------------------------------------------------------------------------

/// The predicate the CLI confirms against is the one the builder acts on.
///
/// `azlin disk repair` prompts before a reformat, and it decides whether to
/// prompt from this. A second copy of the rule in the CLI would eventually ask
/// about a repair that does not reformat, or run one that does without asking.
#[test]
fn the_reformat_predicate_matches_what_the_script_does() {
    for stage in [
        DiskStage::Raw,
        DiskStage::Formatted,
        DiskStage::BackingMounted,
        DiskStage::Healthy,
    ] {
        for force in [false, true] {
            let f = finding("home", 0, stage);
            let predicted = reformats_existing_filesystem(&f, force);
            let script = build_disk_repair_script(&f, USER, force).unwrap_or_default();
            assert_eq!(
                predicted,
                script.contains("--force given; reformatting an existing filesystem"),
                "{stage:?} force={force}:\n{script}"
            );
        }
    }
}

/// `/tmp` has to come back out of `mount -a` writable by everyone.
///
/// The sticky bit is set on the backing directory, one indirection away from
/// the path it governs, so it is asserted rather than argued. An unwritable
/// `/tmp` breaks tmux, agent forwarding and most build tools — a reboot later,
/// far from this command.
#[test]
fn the_tmp_repair_checks_the_sticky_bit_survived() {
    let script = build_disk_repair_script(&finding("tmp", 1, DiskStage::Raw), USER, false).unwrap();
    let mount_a = script.find("sudo mount -a").unwrap();
    let sticky = script
        .find("if [ ! -k /tmp ]; then")
        .unwrap_or_else(|| panic!("no sticky-bit assertion:\n{script}"));
    assert!(mount_a < sticky, "{script}");

    // The home repair has no business asserting anything about /tmp.
    let home = build_disk_repair_script(&finding("home", 0, DiskStage::Raw), USER, false).unwrap();
    assert!(!home.contains("-k /tmp"), "{home}");
}
