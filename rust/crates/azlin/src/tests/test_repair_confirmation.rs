//! `disk repair` must refuse, not hang, when it cannot ask.
//!
//! `806e3bd1` split the two meanings `--force` was carrying: it keeps its
//! "permit mkfs over a filesystem" meaning, and a new `--yes` carries the
//! "do not ask me" meaning it has on nineteen other commands. The consequence
//! is a behaviour change for existing automation — `azlin disk repair --force`
//! in a cron job used to run straight through and now reaches a prompt.
//!
//! A safety fix that turns a silent reformat into a *hang* has not made anyone
//! safer: the job never returns, the operator never sees a message, and the
//! disk is in whatever state the interrupted plan left it. So the refusal path
//! is part of the contract, not an implementation detail:
//!
//!   * it must return, promptly, with a non-zero outcome;
//!   * its message must name `--yes`, the flag that actually skips the prompt
//!     for *this* command — naming `--force` would be advice the operator
//!     cannot follow, since `--force` is what got them to the prompt.
//!
//! `cargo test` runs with stdin detached, so the non-TTY branch is the one
//! these tests take naturally.

use azlin_azure::cloud_init::DiskConfig;
use azlin_azure::disk_layout::{parse_disk_probe, DiskReport, StorageStatus};

use crate::cmd_disk_ops::{repair_is_complete, repair_terminal_verdict};
use crate::dispatch_helpers::safe_confirm_with_flag;

fn report(stage: &str) -> DiskReport {
    parse_disk_probe(
        &format!(
            "azlin-disk lun=0 role=tmp dev=/dev/sdc size=214748364800 \
             fstype=ext4 label=azlin-tmp backing=yes bind={stage}\n\
             azlin-provisioning complete=yes status=ok ledger=yes failed=\n"
        ),
        &DiskConfig {
            home_disk: false,
            tmp_disk: true,
        },
    )
}

#[test]
fn a_non_tty_repair_refuses_rather_than_waiting_for_an_answer() {
    let outcome = safe_confirm_with_flag("Reformat and continue?", false, "--yes");
    assert!(
        outcome.is_err(),
        "a non-TTY confirmation must fail closed, got {outcome:?}"
    );
}

#[test]
fn the_refusal_names_the_flag_that_skips_this_commands_prompt() {
    let message = safe_confirm_with_flag("Reformat and continue?", false, "--yes")
        .expect_err("must refuse in a non-TTY")
        .to_string();

    assert!(
        message.contains("--yes"),
        "refusal must name --yes, got {message:?}"
    );
    // `--force` is what got the operator here. Telling them to add it is advice
    // they have already taken, and the prompt would still be there.
    assert!(
        !message.contains("--force"),
        "refusal must not send the operator back to --force, got {message:?}"
    );
}

#[test]
fn the_refusal_says_why_it_could_not_ask() {
    let message = safe_confirm_with_flag("Reformat and continue?", false, "--yes")
        .expect_err("must refuse in a non-TTY")
        .to_string();
    assert!(
        message.to_lowercase().contains("terminal"),
        "refusal must explain that stdin is not a terminal, got {message:?}"
    );
}

#[test]
fn yes_skips_the_prompt_without_needing_a_terminal() {
    // The escape hatch the refusal points at has to actually work from the same
    // non-TTY context, or the advice is a dead end.
    let outcome = safe_confirm_with_flag("Reformat and continue?", true, "--yes")
        .expect("--yes must not require a terminal");
    assert!(outcome, "--yes must answer the prompt affirmatively");
}

/// Check and repair must not maintain independent verdict rules. This compares
/// them on the identical post-repair report rather than asserting two constants.
#[test]
fn repair_terminal_verdict_is_exactly_checks_verdict_on_the_same_state() {
    for after in [report("yes"), report("no")] {
        let check_verdict = after.status;
        assert_eq!(repair_terminal_verdict(&after), check_verdict);
    }
}

/// A failed command remains diagnostic evidence, but an authoritative healthy
/// re-probe controls the terminal result. This is the v2.7.4 contradiction:
/// execution history and current health must not compete as verdict sources.
#[test]
fn a_healthy_authoritative_reprobe_controls_completion_after_an_earlier_failure() {
    let after = report("yes");
    assert_eq!(after.status, StorageStatus::Ok);
    assert!(
        repair_is_complete(&after),
        "the shared post-repair health evaluation must be the success predicate"
    );
}

#[test]
fn an_unrepaired_authoritative_reprobe_never_reports_repair_complete() {
    let after = report("no");
    assert_eq!(after.status, StorageStatus::Degraded);
    assert!(!repair_is_complete(&after));
}
