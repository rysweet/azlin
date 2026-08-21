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
    parse_disk_probe, roles, DiskFinding, DiskStage, FstabSpec, StorageStatus,
};

const USER: &str = "azureuser";

fn both() -> DiskConfig {
    DiskConfig {
        home_disk: true,
        tmp_disk: true,
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

#[test]
fn a_bind_fstab_line_is_none_bind_zero_zero() {
    let line = fstab_line(&FstabSpec::Bind {
        source: "/mnt/tmp-data/tmp".into(),
        target: "/tmp".into(),
    });
    assert_eq!(line, "/mnt/tmp-data/tmp /tmp none bind 0 0");
    assert!(!line.contains("mode="), "{line}");
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
#[test]
fn the_shared_mkfs_never_reformats_without_asking_blkid_first() {
    let script = blkid_guarded_mkfs("HOME_DEV", Some("azlin-home"));
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
    assert!(
        script.contains("not reformatting"),
        "a skipped format must say so, or a no-op looks like a success:\n{script}"
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

/// Only `formatted` and later can hold data, so only those need `--force`.
#[test]
fn only_formatted_and_later_can_hold_data() {
    assert!(!DiskStage::Absent.holds_data());
    assert!(!DiskStage::Raw.holds_data());
    assert!(DiskStage::Formatted.holds_data());
    assert!(DiskStage::BackingMounted.holds_data());
    assert!(DiskStage::Healthy.holds_data());
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
    let script = build_disk_repair_script(&finding("home", 0, DiskStage::Healthy), USER, false)
        .expect("healthy is not an error");
    assert!(
        script.trim().is_empty(),
        "a healthy disk must produce no script:\n{script}"
    );
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
