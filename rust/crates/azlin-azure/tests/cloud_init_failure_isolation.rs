//! Reachability, ordering and failure-isolation tests for the generated
//! cloud-init script (issue #1131).
//!
//! The suite that shipped this bug had twenty-odd assertions on the *content*
//! of the disk-setup block: it has a retry loop, it has a rollback trap, it
//! rsyncs, it writes fstab by UUID. Every one of them passed on a script whose
//! disk block never executed, because `apt-get install` failed three commands
//! earlier and `set -euo pipefail` ended the script there.
//!
//! Content assertions cannot catch that. These tests assert two things content
//! tests structurally cannot:
//!
//! * **Ordering** — the disk block is emitted before anything that needs the
//!   network, checked by byte offset in the generated script.
//! * **Reachability** — the disk block actually runs, and the script actually
//!   survives, when the package install fails. Checked by running the generated
//!   script in a real shell against failing shims and reading back the order in
//!   which commands were invoked.
//!
//! See `docs-site/storage/data-disk-layout.md` for the contract these assert.

use azlin_azure::cloud_init::{render_dev_cloud_init_script_with_disks, DiskConfig};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const USER: &str = "azureuser";

fn both_disks() -> DiskConfig {
    DiskConfig {
        home_disk: true,
        tmp_disk: true,
    }
}

fn render(config: &DiskConfig) -> String {
    render_dev_cloud_init_script_with_disks(USER, config)
}

fn index_of(script: &str, needle: &str) -> usize {
    script.find(needle).unwrap_or_else(|| {
        panic!("expected {needle:?} somewhere in the generated script:\n{script}")
    })
}

/// The marker that opens a failure-isolated section.
fn section_marker(name: &str) -> String {
    format!("# ---- section: {name} ----")
}

/// Split the script into `(name, body)` pairs, one per section marker.
///
/// Anything before the first marker is the preamble (shebang, `set -euo
/// pipefail`, the `azlin_record` helper) and is deliberately excluded: it is
/// not a section and must not be wrapped like one.
fn sections(script: &str) -> Vec<(String, String)> {
    const OPEN: &str = "# ---- section: ";
    const CLOSE: &str = " ----";

    let mut out = Vec::new();
    let mut rest = script;
    while let Some(start) = rest.find(OPEN) {
        let after_open = &rest[start + OPEN.len()..];
        let name_end = after_open.find(CLOSE).unwrap_or_else(|| {
            panic!(
                "malformed section marker near:\n{}",
                &after_open[..40.min(after_open.len())]
            )
        });
        let name = after_open[..name_end].to_string();
        let body_start = start + OPEN.len() + name_end + CLOSE.len();
        let body_rel = &rest[body_start..];
        let body_end = body_rel.find(OPEN).unwrap_or(body_rel.len());
        out.push((name, body_rel[..body_end].to_string()));
        rest = &rest[body_start + body_end..];
    }
    out
}

fn section_body(script: &str, name: &str) -> String {
    sections(script)
        .into_iter()
        .find(|(n, _)| n == name)
        .unwrap_or_else(|| {
            panic!(
                "no section named {name:?}; the script has {:?}",
                sections(script)
                    .into_iter()
                    .map(|(n, _)| n)
                    .collect::<Vec<_>>()
            )
        })
        .1
}

// ---------------------------------------------------------------------------
// F1 — ordering
// ---------------------------------------------------------------------------

/// The defect in one assertion.
///
/// Disk setup needs `udevadm`, `mkfs.ext4`, `blkid` and `mount`, all present in
/// the Azure Ubuntu base image, and no network at all. Package installation
/// needs the archive to be reachable, which on a bastion-only VM with no
/// outbound route it is not. Sequencing the step that cannot fail for network
/// reasons behind the step that can is the whole bug.
#[test]
fn disk_setup_is_emitted_before_the_first_apt_command() {
    let script = render(&both_disks());

    let disk_home = index_of(&script, &section_marker("disk-home"));
    let disk_tmp = index_of(&script, &section_marker("disk-tmp"));
    let apt_update = index_of(&script, "apt-get update");
    let apt_install = index_of(&script, "apt-get install");

    assert!(
        disk_home < apt_update,
        "the home-disk section must be emitted before `apt-get update` \
         (home at {disk_home}, apt-get update at {apt_update}):\n{script}"
    );
    assert!(
        disk_tmp < apt_update,
        "the tmp-disk section must be emitted before `apt-get update` \
         (tmp at {disk_tmp}, apt-get update at {apt_update}):\n{script}"
    );
    assert!(
        apt_update < apt_install,
        "apt-get update must still precede apt-get install:\n{script}"
    );
}

/// Ordering that only holds against `apt` is ordering that breaks the next time
/// somebody adds a step. Nothing that touches the network may precede the disk
/// sections.
#[test]
fn disk_setup_is_emitted_before_every_network_dependent_step() {
    let script = render(&both_disks());
    let disk_home = index_of(&script, &section_marker("disk-home"));

    for network_step in [
        "apt-get update",
        "apt-get upgrade",
        "apt-get install",
        "add-apt-repository",
        "curl ",
        "wget ",
        "snap install",
    ] {
        let at = index_of(&script, network_step);
        assert!(
            disk_home < at,
            "disk setup (offset {disk_home}) must precede the network-dependent \
             step {network_step:?} (offset {at}); a network failure there must \
             not be able to strand the data disks:\n{script}"
        );
    }
}

// ---------------------------------------------------------------------------
// F3 — failure isolation
// ---------------------------------------------------------------------------

/// Every section must use the `rc=0; ( … ) || rc=$?` form.
///
/// The `||` list is what stops `set -e` from ending the script, and `rc=0`
/// before the group is what keeps `rc` defined under `set -u`. Writing
/// `( … ); rc=$?` instead — the obvious-looking alternative — aborts on the
/// group and never reaches the assignment.
#[test]
fn every_section_is_wrapped_so_its_failure_cannot_end_the_script() {
    let script = render(&both_disks());
    let found = sections(&script);
    assert!(
        !found.is_empty(),
        "the script emits no `# ---- section: … ----` markers at all:\n{script}"
    );

    for (name, body) in &found {
        assert!(
            body.trim_start().starts_with("rc=0"),
            "section {name:?} must set `rc=0` before the group, so `$rc` is \
             defined under `set -u` even if the group is skipped:\n{body}"
        );
        assert!(
            body.contains(") || rc=$?"),
            "section {name:?} must close with `) || rc=$?`; a bare `( … )` on \
             its own line aborts the script under `set -e` before any status \
             can be recorded:\n{body}"
        );
        assert!(
            body.contains(&format!("azlin_record {name} \"$rc\"")),
            "section {name:?} must record its outcome to the ledger:\n{body}"
        );
    }
}

/// `set +e` inside a section would let execution continue past a failed
/// `mount --bind` to the `rm -rf /home/<user>.old` cleanup, deleting the only
/// copy of the original home directory. That is a data-loss difference, not a
/// style one: the rollback trap depends on the subshell stopping at its first
/// failing command.
#[test]
fn no_section_disables_errexit_inside_the_subshell() {
    let script = render(&both_disks());
    assert!(
        !script.contains("set +e"),
        "failure isolation must come from `|| rc=$?` at the section boundary, \
         never from `set +e` inside it:\n{script}"
    );
    assert!(
        !script.contains("|| true\n) || rc=$?"),
        "a section whose last command is `|| true` reports success regardless \
         of what happened inside it:\n{script}"
    );
}

/// The file default stays fail-fast. Only the section boundary is permeable.
#[test]
fn the_script_still_fails_fast_by_default() {
    let script = render(&both_disks());
    let head: String = script.lines().take(3).collect::<Vec<_>>().join("\n");
    assert!(
        head.contains("set -euo pipefail"),
        "critical work must still abort on the first error; only optional \
         sections are isolated:\n{head}"
    );
}

/// Section names are printed back by `azlin disk check` and are written into
/// support instructions, so they are a contract. This test is the thing that
/// fails when a new section drifts from
/// `docs-site/storage/data-disk-layout.md`.
#[test]
fn the_emitted_section_names_are_the_documented_contract() {
    let script = render(&both_disks());
    let names: Vec<String> = sections(&script).into_iter().map(|(n, _)| n).collect();

    for required in [
        "disk-home",
        "disk-tmp",
        "apt-update",
        "apt-upgrade",
        "apt-install",
    ] {
        assert!(
            names.iter().any(|n| n == required),
            "the documented section {required:?} is missing; emitted: {names:?}"
        );
    }

    for name in &names {
        assert!(
            !name.chars().any(char::is_whitespace),
            "section name {name:?} contains whitespace and would corrupt the \
             tab-separated ledger"
        );
        let documented = matches!(
            name.as_str(),
            "disk-home" | "disk-tmp" | "apt-update" | "apt-upgrade" | "apt-install"
        ) || (name.starts_with("setup-")
            && name[6..]
                .chars()
                .all(|c| c.is_ascii_lowercase() || c.is_ascii_digit() || c == '-')
            && name.len() > 6);
        assert!(
            documented,
            "section {name:?} is neither one of the documented core sections \
             nor a `setup-<tool>` section; either rename it or update \
             docs-site/storage/data-disk-layout.md"
        );
    }

    let mut sorted = names.clone();
    sorted.sort();
    sorted.dedup();
    assert_eq!(
        sorted.len(),
        names.len(),
        "section names must be unique — the ledger is keyed by them: {names:?}"
    );
}

/// Sections exist even with no data disks; the apt sections are the ones that
/// broke, and they break the same way on a VM with no disks at all.
#[test]
fn the_apt_sections_are_isolated_even_when_no_data_disks_are_configured() {
    let script = render(&DiskConfig::default());
    let names: Vec<String> = sections(&script).into_iter().map(|(n, _)| n).collect();
    assert!(
        names.iter().any(|n| n == "apt-install"),
        "emitted: {names:?}\n{script}"
    );
    assert!(
        !names.iter().any(|n| n.starts_with("disk-")),
        "no disk sections without disks: {names:?}"
    );
}

// ---------------------------------------------------------------------------
// F4 — the ledger and the terminal state
// ---------------------------------------------------------------------------

/// Suppressing failures without recording them is worse than the original bug:
/// it makes the sentinel reachable on every path, so a VM with no home disk
/// reports "complete".
#[test]
fn the_script_writes_a_ledger_and_both_terminal_state_files() {
    let script = render(&both_disks());
    for path in [
        "/var/lib/azlin/provisioning.tsv",
        "/var/lib/azlin/provisioning-complete",
        "/var/lib/azlin/provisioning-status",
    ] {
        assert!(script.contains(path), "{path} is never written:\n{script}");
    }
    assert!(
        script.contains("azlin_record()"),
        "the ledger writer must be defined once in the preamble, not inlined \
         per section:\n{script}"
    );
    assert!(
        script.contains("[AZLIN] section="),
        "each section outcome must also reach cloud-init-output.log:\n{script}"
    );
}

/// `azlin_record` is called with `0`, a numeric status, or the literal
/// `skipped`. A `[ "$rc" = 0 ]` test alone renders the third as `failed`.
#[test]
fn the_ledger_writer_handles_the_skipped_status() {
    let script = render(&both_disks());
    let preamble = &script[..index_of(&script, "# ---- section: ")];
    assert!(
        preamble.contains("skipped"),
        "azlin_record must have a branch for a section skipped because its \
         dependency failed, distinct from `failed`:\n{preamble}"
    );
}

// ---------------------------------------------------------------------------
// The `mode=1777` trap
// ---------------------------------------------------------------------------

/// `mode=` is a tmpfs option. ext4 rejects the mount outright, and combined
/// with `nofail` the rejection is silent: boot succeeds and the mount point
/// quietly stays on the OS disk.
#[test]
fn no_ext4_fstab_line_carries_a_mode_option() {
    let script = render(&both_disks());
    let fstab_lines: Vec<&str> = script
        .lines()
        .filter(|l| l.contains("/etc/fstab") && l.contains(" ext4 "))
        .collect();
    assert!(
        !fstab_lines.is_empty(),
        "expected the script to write ext4 fstab entries:\n{script}"
    );
    for line in fstab_lines {
        assert!(
            !line.contains("mode="),
            "`mode=` is a tmpfs option; ext4 rejects it and `nofail` makes the \
             rejection silent: {line}"
        );
        assert!(
            line.contains("defaults,nofail"),
            "ext4 data-disk entries are `defaults,nofail 0 2` and nothing \
             else: {line}"
        );
    }
}

/// The sticky bit is a `chmod`, and it belongs on the backing directory. A
/// `chmod 1777 /tmp` on a running VM reaches the same inode through the bind
/// and looks correct — until the next boot brings `/tmp` up with whatever mode
/// the backing directory actually has.
#[test]
fn the_tmp_sticky_bit_is_applied_to_the_backing_directory() {
    let script = render(&both_disks());
    let tmp = section_body(&script, "disk-tmp");
    assert!(
        tmp.contains("chmod 1777 /mnt/tmp-data/tmp"),
        "the sticky bit must be set on the backing directory so it survives a \
         reboot:\n{tmp}"
    );
}

// ---------------------------------------------------------------------------
// F2 — the copy step after the reorder
// ---------------------------------------------------------------------------

/// Moving the disk block above `apt-get install` removes the only thing that
/// guaranteed `rsync` was installed — it is in `default_dev_packages()`, not in
/// the base image. An unguarded `rsync` there would abort the home subshell on
/// exactly the VMs this fix exists for.
///
/// This replaces `test_disk_home_block_has_mandatory_rsync`, keeping its intent
/// — the home copy cannot silently fail — and adding the fallback the reorder
/// requires.
#[test]
fn the_home_copy_falls_back_to_cp_and_is_never_silently_suppressed() {
    let script = render(&both_disks());
    let home = section_body(&script, "disk-home");

    assert!(
        home.contains("command -v rsync"),
        "the copy must choose its tool at runtime; `rsync` is not in the base \
         image and the disk block now runs before apt:\n{home}"
    );
    assert!(home.contains("rsync -aAX"), "{home}");
    assert!(
        home.contains("cp -a"),
        "`cp -a` (= `-dR --preserve=all`) is in coreutils and covers the \
         xattr/ACL intent of `-aAX`:\n{home}"
    );

    for line in home
        .lines()
        .filter(|l| l.contains("rsync -aAX") || l.contains("cp -a"))
    {
        assert!(
            !line.contains("|| true"),
            "the home copy must never be unconditionally suppressed — a \
             silently skipped copy binds an empty directory over the user's \
             home: {line}"
        );
        assert!(
            !line.contains("2>/dev/null"),
            "the home copy must not hide its own errors: {line}"
        );
    }
}

/// The tmp copy is best-effort by design — `/tmp` contents are disposable —
/// and that asymmetry should be visible rather than accidental.
#[test]
fn the_tmp_copy_stays_best_effort() {
    let script = render(&both_disks());
    let tmp = section_body(&script, "disk-tmp");
    let copy = tmp
        .lines()
        .find(|l| l.contains("rsync") || l.contains("cp -a"))
        .unwrap_or_else(|| panic!("no copy step in the tmp section:\n{tmp}"));
    assert!(
        copy.contains("|| true"),
        "losing /tmp contents must not fail the tmp disk setup: {copy}"
    );
}

// ---------------------------------------------------------------------------
// Runtime: the script actually runs, in a real shell
// ---------------------------------------------------------------------------

#[cfg(unix)]
mod real_shell {
    use super::*;
    use std::path::{Path, PathBuf};
    use std::process::Command;
    use std::time::{SystemTime, UNIX_EPOCH};

    /// Commands the generated script invokes that the harness stands in for.
    ///
    /// Each shim appends its own name to an order log, so the test can assert
    /// the order things *ran* in, not just the order they were written in.
    ///
    /// `mv`, `rm` and `cp` are shimmed for safety rather than observation: the
    /// disk block moves and deletes home directories, and a test that runs as
    /// root — which is normal inside a CI container — must not be one `mkfs`
    /// away from destroying the machine it runs on. Path rewriting below keeps
    /// the script inside a scratch directory; these shims are the second layer.
    ///
    /// `readlink` returns nothing, so LUN detection fails the same way on every
    /// machine. Without it this test passes or fails depending on whether the
    /// host happens to be an Azure VM with data disks attached.
    const SHIMMED: &[&str] = &[
        "udevadm",
        "readlink",
        "mkfs.ext4",
        "mount",
        "mountpoint",
        "blkid",
        "lsblk",
        "rsync",
        "mv",
        "rm",
        "cp",
        "chmod",
        "chown",
        "sleep",
        "apt",
        "add-apt-repository",
        "curl",
        "wget",
        "snap",
        "su",
        "systemctl",
        "usermod",
        "loginctl",
        "gpg",
        "dpkg",
        "lsb_release",
        "tee",
        "tar",
        "ln",
        "node",
        "gh",
        "az",
        "dotnet",
        "rustc",
        "which",
    ];

    struct Outcome {
        status_ok: bool,
        order: Vec<String>,
        ledger: String,
        sentinel_present: bool,
        provisioning_status: Option<String>,
        output: String,
    }

    impl Outcome {
        fn ledger_status(&self, section: &str) -> Option<String> {
            self.ledger.lines().find_map(|line| {
                let mut f = line.split('\t');
                match (f.next(), f.next()) {
                    (Some(name), Some(status)) if name == section => Some(status.to_string()),
                    _ => None,
                }
            })
        }

        fn ran_before(&self, first: &str, second: &str) -> bool {
            match (
                self.order.iter().position(|c| c == first),
                self.order.iter().position(|c| c == second),
            ) {
                (Some(a), Some(b)) => a < b,
                _ => false,
            }
        }
    }

    fn scratch() -> PathBuf {
        let unique = format!(
            "azlin-cloud-init-run-{}-{}",
            std::process::id(),
            SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .expect("system clock before unix epoch")
                .as_nanos()
        );
        let root = std::env::temp_dir().join(unique);
        std::fs::create_dir_all(&root).expect("create scratch root");
        root
    }

    /// Shell functions that stand in for every external command the script
    /// reaches. Functions rather than PATH entries because the script runs its
    /// sections in `( … )` subshells, which inherit functions.
    ///
    /// `command_not_found_handle` catches anything not listed: bash calls it in
    /// non-interactive shells too, so an unshimmed command becomes a logged
    /// no-op rather than a 127 that would end the script for the wrong reason.
    fn shims(order_log: &Path, apt_rc: i32) -> String {
        let log = order_log.display();
        let mut out = format!(
            "azlin_test_log() {{ printf '%s\\n' \"$1\" >> '{log}'; }}\n\
             command_not_found_handle() {{ azlin_test_log \"$1\"; return 0; }}\n\
             apt-get() {{ azlin_test_log apt-get; return {apt_rc}; }}\n"
        );
        for cmd in SHIMMED {
            // `sleep` must be instant: the LUN retry loop is 12 × 5s and the
            // test must not wait a minute to learn the block was reached.
            out.push_str(&format!("{cmd}() {{ azlin_test_log {cmd}; return 0; }}\n"));
        }
        out
    }

    /// Absolute paths the generated script writes to, redirected into the
    /// scratch directory so an unprivileged *and* a root test both stay inside
    /// it. Longest-first, because `/mnt/home-data` must be rewritten before
    /// anything that could match a prefix of it.
    const REDIRECTED: &[&str] = &[
        "/var/lib/azlin",
        "/mnt/home-data",
        "/mnt/tmp-data",
        "/usr/share/dotnet",
        "/usr/local/bin",
        "/etc/fstab",
        "/etc/apt",
        "/home/azureuser",
    ];

    /// Rewrite every absolute path the script writes to so it lands under
    /// `root`. Returns the rewritten script.
    ///
    /// This is the one liberty the harness takes with "run the generated script
    /// verbatim", and it is not optional: the script's job is to format disks
    /// and move home directories. Everything that decides *control flow* — the
    /// section wrappers, the ordering, the exit statuses — runs unmodified.
    fn redirect_paths(script: &str, root: &Path) -> String {
        let mut out = script.to_string();
        for path in REDIRECTED {
            assert!(
                out.contains(path),
                "the generated script no longer writes to {path}; drop it from \
                 REDIRECTED rather than leaving a substitution that silently \
                 no-ops"
            );
            let target = root.join(path.trim_start_matches('/').replace('/', "-"));
            out = out.replace(path, target.to_str().expect("utf-8 path"));
        }
        out
    }

    /// Runs the generated script under bash with failing/succeeding apt shims.
    ///
    /// Returns `None` when bash is unavailable, so the caller can skip rather
    /// than fail on a machine that cannot run the harness.
    fn run_generated_script(config: &DiskConfig, apt_rc: i32) -> Option<Outcome> {
        if Command::new("bash").arg("-c").arg("true").output().is_err() {
            return None;
        }

        let root = scratch();
        let var_lib = root.join("var-lib-azlin");
        let order_log = root.join("order.log");
        let script_path = root.join("part-001.sh");

        let runnable = redirect_paths(&render(config), &root);
        assert!(
            !runnable.contains("/etc/fstab"),
            "a path escaped the redirect and the test would write to the real \
             /etc/fstab"
        );
        std::fs::write(&script_path, &runnable).expect("write generated script");

        let harness = format!(
            "{}\nsource '{}'\n",
            shims(&order_log, apt_rc),
            script_path.display()
        );

        let out = Command::new("bash")
            .arg("-c")
            .arg(&harness)
            .current_dir(&root)
            .output()
            .expect("failed to run bash");

        let outcome = Outcome {
            status_ok: out.status.success(),
            order: std::fs::read_to_string(&order_log)
                .unwrap_or_default()
                .lines()
                .map(str::to_string)
                .collect(),
            ledger: std::fs::read_to_string(var_lib.join("provisioning.tsv")).unwrap_or_default(),
            sentinel_present: var_lib.join("provisioning-complete").exists(),
            provisioning_status: std::fs::read_to_string(var_lib.join("provisioning-status"))
                .ok()
                .map(|s| s.trim().to_string()),
            output: String::from_utf8_lossy(&out.stdout).to_string()
                + &String::from_utf8_lossy(&out.stderr),
        };

        let _ = std::fs::remove_dir_all(&root);
        Some(outcome)
    }

    /// The generated script must be valid shell before any of this means
    /// anything.
    #[test]
    fn the_generated_script_parses() {
        let root = scratch();
        let path = root.join("part-001.sh");
        std::fs::write(&path, render(&both_disks())).expect("write script");
        let out = Command::new("bash")
            .arg("-n")
            .arg(&path)
            .output()
            .expect("failed to run bash -n");
        let stderr = String::from_utf8_lossy(&out.stderr).to_string();
        let _ = std::fs::remove_dir_all(&root);
        assert!(
            out.status.success(),
            "bash -n rejected the script: {stderr}"
        );
    }

    /// The headline regression test for #1131.
    ///
    /// `apt-get` exits non-zero, exactly as it did on the bastion-only VM with
    /// no outbound route. The disk block must still have run, and the proof is
    /// that `udevadm` — the first command inside the disk subshell — appears in
    /// the order log, and appears *before* `apt-get`.
    #[test]
    fn the_disk_block_runs_even_though_the_package_install_fails() {
        let Some(outcome) = run_generated_script(&both_disks(), 100) else {
            eprintln!("skipping: bash unavailable");
            return;
        };

        assert!(
            outcome.order.iter().any(|c| c == "udevadm"),
            "the disk block never executed. Commands that ran: {:?}\n{}",
            outcome.order,
            outcome.output
        );
        assert!(
            outcome.ran_before("udevadm", "apt-get"),
            "disk setup must run before apt, so a failing archive cannot \
             strand the data disks. Order: {:?}",
            outcome.order
        );
    }

    /// A missing `tree` package must not be able to end provisioning.
    #[test]
    fn the_script_survives_a_non_zero_exit_from_the_package_section() {
        let Some(outcome) = run_generated_script(&both_disks(), 100) else {
            eprintln!("skipping: bash unavailable");
            return;
        };

        assert!(
            outcome.status_ok,
            "a failing apt section must not end the script:\n{}",
            outcome.output
        );
        assert_eq!(
            outcome.ledger_status("apt-install").as_deref(),
            Some("failed"),
            "the failure must be recorded, not swallowed. Ledger:\n{}",
            outcome.ledger
        );
    }

    /// The tail of the #1131 failure: the sentinel was never written, so the VM
    /// sat in "provisioning" forever with no terminal state and no explanation.
    /// Every path must now reach a terminal state — and a degraded one must say
    /// so.
    #[test]
    fn a_failed_run_still_reaches_a_terminal_state_and_reports_degraded() {
        let Some(outcome) = run_generated_script(&both_disks(), 100) else {
            eprintln!("skipping: bash unavailable");
            return;
        };

        assert!(
            outcome.sentinel_present,
            "provisioning-complete must be written on every path, or readiness \
             checks poll forever:\n{}",
            outcome.output
        );
        assert_eq!(
            outcome.provisioning_status.as_deref(),
            Some("degraded"),
            "a run whose sections failed must not report `ok`. Ledger:\n{}",
            outcome.ledger
        );
    }

    /// The disk sections fail here (an unprivileged test has no block device at
    /// LUN 0). That failure must be *recorded* — this is the assertion that
    /// stops "isolate the failure" from degenerating into "hide the failure".
    #[test]
    fn a_failed_disk_section_is_recorded_rather_than_swallowed() {
        let Some(outcome) = run_generated_script(&both_disks(), 0) else {
            eprintln!("skipping: bash unavailable");
            return;
        };

        assert_eq!(
            outcome.ledger_status("disk-home").as_deref(),
            Some("failed"),
            "ledger:\n{}\noutput:\n{}",
            outcome.ledger,
            outcome.output
        );
        assert_eq!(
            outcome.provisioning_status.as_deref(),
            Some("degraded"),
            "a VM with no home disk must not report `ok`:\n{}",
            outcome.ledger
        );
    }

    /// The mirror image: when apt succeeds, its sections must record `ok`.
    /// Without this, "everything is always degraded" would pass the tests
    /// above.
    #[test]
    fn successful_sections_are_recorded_as_ok() {
        let Some(outcome) = run_generated_script(&DiskConfig::default(), 0) else {
            eprintln!("skipping: bash unavailable");
            return;
        };

        assert!(outcome.status_ok, "{}", outcome.output);
        for section in ["apt-update", "apt-upgrade", "apt-install"] {
            assert_eq!(
                outcome.ledger_status(section).as_deref(),
                Some("ok"),
                "section {section} should be ok. Ledger:\n{}",
                outcome.ledger
            );
        }
        assert!(outcome.sentinel_present);
    }
}
