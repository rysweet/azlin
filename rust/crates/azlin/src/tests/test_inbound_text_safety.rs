//! Every reader of VM-supplied text applies the same rule.
//!
//! `806e3bd1` closed this at the storage probe's parse boundary: the device
//! path, the filesystem label and the provisioning status are all
//! root-controlled on the VM, and all three land in an operator's terminal, so
//! anything that can move a cursor is stripped once, where the line is parsed.
//!
//! It closed it at *one* boundary. Two more readers of the same wire take the
//! same text and print it raw:
//!
//!   * `auth_forward::failed_sections` reads the `azlin_failed_sections:` line
//!     — the same `provisioning.tsv` ledger, the same `$2=="failed"` rule —
//!     and `println!`s each name during `azlin new`.
//!   * the storage probe's failure path prints the VM's *stderr*, which gets
//!     `sanitize()` (secret redaction) but never the control-character strip.
//!     The asymmetry with stdout is accidental, and stderr is the channel an
//!     attacker shapes more easily.
//!
//! These tests are the contract for closing both against one shared predicate
//! rather than a third private copy. See `azlin_core::sanitizer::printable`.
//!
//! Threat framing, so the bar is not mistaken for a stronger one: azlin grants
//! no privilege the operator does not already hold, and none of this defends a
//! VM against its own root. What it stops is one machine's output rewriting the
//! report of the machines listed after it in a fleet-wide sweep.

use crate::auth_forward::failed_sections;
use crate::cmd_disk_ops::probe_failure_note;

// ---------------------------------------------------------------------------
// The second reader: failed section names printed during `azlin new`
// ---------------------------------------------------------------------------

#[test]
fn failed_section_names_survive_unchanged_when_they_are_ordinary() {
    let output = "status: azlin-degraded\nazlin_failed_sections: disk-home,apt-install\n";
    assert_eq!(failed_sections(output), vec!["disk-home", "apt-install"]);
}

#[test]
fn a_section_name_cannot_repaint_the_provisioning_report() {
    // `azlin new` prints one line per failed section and then the "check the
    // storage layout" advice. A CR in a section name overwrites the line it was
    // printed on; the ANSI erase takes the rest.
    let output =
        "status: azlin-degraded\nazlin_failed_sections: disk-home\r\x1b[2KProvisioning OK,apt\x08\n";

    for name in failed_sections(output) {
        assert!(
            !name.chars().any(char::is_control),
            "control character reached the terminal in {name:?}"
        );
    }
}

#[test]
fn a_section_name_cannot_reorder_the_line_it_is_printed_on() {
    // Category Cf, which `char::is_control()` does not answer for.
    let output = "status: azlin-degraded\nazlin_failed_sections: disk-\u{202e}emoh\u{202c}\n";

    let names = failed_sections(output);
    assert_eq!(
        names,
        vec!["disk-emoh"],
        "bidi override reached the terminal"
    );
}

#[test]
fn a_section_name_stripped_to_nothing_is_dropped_not_printed_blank() {
    // A name that was *only* control characters must not become a "failed
    // section: " line with nothing after it — that reads as a bug in azlin
    // rather than as a hostile label, and it is the empty-name case the
    // existing filter already handles for whitespace.
    let output = "status: azlin-degraded\nazlin_failed_sections: \u{202e},disk-tmp,\r\n";
    assert_eq!(failed_sections(output), vec!["disk-tmp"]);
}

#[test]
fn no_failed_sections_line_is_no_sections() {
    assert!(failed_sections("status: azlin-ok\n").is_empty());
    assert!(failed_sections("status: azlin-ok\nazlin_failed_sections: \n").is_empty());
}

// ---------------------------------------------------------------------------
// The third reader: the storage probe's stderr bail
// ---------------------------------------------------------------------------
//
// `run_probe` is network-bound and cannot be unit-tested, so the message it
// prints is built by a pure function and the I/O stays in the caller. That seam
// is the point: the rule lives somewhere a test can reach it.

#[test]
fn the_probe_failure_note_names_the_vm_and_quotes_the_reason() {
    let note = probe_failure_note("web-01", "sudo: a password is required");
    assert!(note.contains("web-01"), "{note:?}");
    assert!(note.contains("sudo: a password is required"), "{note:?}");
}

#[test]
fn the_probe_failure_note_still_redacts_secrets() {
    // The existing `sanitize()` behaviour must not be lost when the strip is
    // added — this is the regression that a naive "just wrap it in printable"
    // would cause if the composition order were reversed.
    let note = probe_failure_note(
        "web-01",
        "az failed: AccountKey=dGhpcyBpcyBhIHRlc3Qga2V5IHZhbHVl",
    );
    assert!(note.contains("REDACTED"), "{note:?}");
    assert!(!note.contains("dGhpcyB"), "{note:?}");
}

#[test]
fn the_probe_failure_note_cannot_move_the_cursor() {
    let note = probe_failure_note(
        "web-01",
        "denied\r\x1b[2Kstorage probe on 'web-02' failed: ok",
    );
    assert!(
        !note.chars().any(char::is_control),
        "control character reached the terminal in {note:?}"
    );
}

#[test]
fn the_probe_failure_note_cannot_reorder_the_fleet_report() {
    let note = probe_failure_note("web-01", "\u{202e}dekcolb\u{202c}");
    assert!(
        !note.contains('\u{202e}') && !note.contains('\u{202c}'),
        "bidi override reached the terminal in {note:?}"
    );
}

#[test]
fn the_probe_failure_note_cleans_the_vm_name_too() {
    // The name is read back from `az vm list`, not from azlin's own create
    // path: a VM put into the resource group by any other means carries
    // whatever name it was given. It is interpolated into the same line as the
    // reason, so exempting it would leave the hole open one field to the left.
    let note = probe_failure_note("web-01\r\x1b[2Kall probes ok", "denied");
    assert!(
        !note.chars().any(char::is_control),
        "control character reached the terminal in {note:?}"
    );
    assert!(note.contains("web-01"), "the real name was lost: {note:?}");
}

#[test]
fn an_empty_reason_still_produces_a_usable_note() {
    // A probe that died without saying anything must not print a dangling
    // "failed: " — the VM name is the part the operator needs.
    let note = probe_failure_note("web-01", "");
    assert!(note.contains("web-01"), "{note:?}");
    assert!(!note.trim().ends_with(':'), "dangling colon: {note:?}");
}
