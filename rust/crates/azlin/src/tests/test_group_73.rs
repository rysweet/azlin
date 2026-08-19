//! Regression tests for the destructive/security-relevant flags of issue #1089
//! that clap accepted, `--help` advertised, and the handlers then discarded.
//!
//! Covered here:
//!   1. `env list --show-values`  — values must be masked unless asked for
//!   2. `restore --dry-run`       — must preview and restore nothing
//!   3. `batch stop --no-deallocate` — must stop, not deallocate
//!   4. `batch --vm-pattern` / `--all` — must filter, and must never describe a
//!      discarded or absent filter with an innocuous word
//!
//! Everything here runs without Azure. The subprocess cases use
//! [`run_isolated`], which points `AZLIN_CONFIG_DIR` at a tempdir so they can
//! never touch the developer's real `~/.azlin/config.toml` (issue #1079).

use super::common::*;
use tempfile::TempDir;

// ═══════════════════════════════════════════════════════════════════════
// 1. env list --show-values
// ═══════════════════════════════════════════════════════════════════════

const FAKE_ENV_OUTPUT: &str =
    "ANTHROPIC_API_KEY=sk-ant-api03-supersecretvalue\nGITHUB_TOKEN=ghp_notarealtoken\nLANG=C.UTF-8\n";

/// The default (`--show-values` absent) must not print any secret in full.
#[test]
fn test_env_list_masks_values_by_default() {
    let rows = crate::env_helpers::env_display_rows(FAKE_ENV_OUTPUT, false);
    assert_eq!(rows.len(), 3);
    let rendered = rows
        .iter()
        .map(|(k, v)| format!("{}={}", k, v))
        .collect::<Vec<_>>()
        .join("\n");

    // Keys stay visible — masking must not make the listing useless.
    assert!(rendered.contains("ANTHROPIC_API_KEY"));
    assert!(rendered.contains("GITHUB_TOKEN"));

    // Values must not be recoverable from the output.
    assert!(
        !rendered.contains("supersecretvalue"),
        "secret leaked into masked output: {rendered}"
    );
    assert!(
        !rendered.contains("notarealtoken"),
        "token leaked into masked output: {rendered}"
    );
    assert!(!rendered.contains("C.UTF-8"));
}

/// `--show-values` is the escape hatch and must print values verbatim.
#[test]
fn test_env_list_show_values_reveals_full_values() {
    let rows = crate::env_helpers::env_display_rows(FAKE_ENV_OUTPUT, true);
    assert_eq!(
        rows,
        vec![
            (
                "ANTHROPIC_API_KEY".to_string(),
                "sk-ant-api03-supersecretvalue".to_string()
            ),
            ("GITHUB_TOKEN".to_string(), "ghp_notarealtoken".to_string()),
            ("LANG".to_string(), "C.UTF-8".to_string()),
        ]
    );
}

/// A short value is redacted whole: a prefix of it would be most of it.
#[test]
fn test_mask_env_value_short_is_fully_redacted() {
    let masked = crate::env_helpers::mask_env_value("hunter2");
    assert_eq!(masked, "********");
    assert!(!masked.contains("hunter"));
}

/// A long value keeps a four-character hint and nothing more, so two
/// credentials can be told apart without either being usable.
#[test]
fn test_mask_env_value_long_leaks_at_most_four_characters() {
    let secret = "sk-ant-api03-supersecretvalue";
    let masked = crate::env_helpers::mask_env_value(secret);
    assert!(masked.starts_with("sk-a"), "got {masked}");
    assert!(!masked.contains("supersecret"));
    // Only the 4-char prefix of the original survives.
    let leaked = masked.trim_end_matches('*');
    assert_eq!(leaked.len(), 4);
    assert!(secret.starts_with(leaked));
}

/// An empty value has nothing to hide and must not render as a fake secret.
#[test]
fn test_mask_env_value_empty_stays_empty() {
    assert_eq!(crate::env_helpers::mask_env_value(""), "");
}

/// Masking must not silently drop variables.
#[test]
fn test_env_display_rows_preserves_every_key() {
    let masked = crate::env_helpers::env_display_rows(FAKE_ENV_OUTPUT, false);
    let shown = crate::env_helpers::env_display_rows(FAKE_ENV_OUTPUT, true);
    let masked_keys: Vec<&String> = masked.iter().map(|(k, _)| k).collect();
    let shown_keys: Vec<&String> = shown.iter().map(|(k, _)| k).collect();
    assert_eq!(masked_keys, shown_keys);
}

/// The footer has to tell the user the escape hatch exists.
#[test]
fn test_masked_values_hint_names_the_flag() {
    let hint = crate::env_helpers::masked_values_hint(3);
    assert!(hint.contains("--show-values"));
    assert!(hint.contains('3'));
}

/// `--show-values` still reaches `--help`.
#[test]
fn test_env_list_help_still_advertises_show_values() {
    let dir = TempDir::new().unwrap();
    let out = run_isolated(&dir, &["env", "list", "--help"]);
    let combined = format!(
        "{}{}",
        String::from_utf8_lossy(&out.stdout),
        String::from_utf8_lossy(&out.stderr)
    );
    assert!(combined.contains("--show-values"), "{combined}");
    assert!(combined.contains("masked"), "{combined}");
}

// ═══════════════════════════════════════════════════════════════════════
// 2. restore --dry-run
// ═══════════════════════════════════════════════════════════════════════

fn sessions(pairs: &[(&str, &[&str])]) -> std::collections::HashMap<String, Vec<String>> {
    pairs
        .iter()
        .map(|(vm, s)| {
            (
                vm.to_string(),
                s.iter().map(|x| x.to_string()).collect::<Vec<String>>(),
            )
        })
        .collect()
}

/// The plan expands every session on every VM, in a stable order.
#[test]
fn test_plan_restore_expands_all_sessions() {
    let plan = crate::restore_helpers::plan_restore(&sessions(&[
        ("vm-b", &["build:1"]),
        ("vm-a", &["main:1", "dev:0"]),
    ]));
    let pairs: Vec<(String, String)> = plan
        .targets
        .iter()
        .map(|t| (t.vm.clone(), t.session.clone()))
        .collect();
    assert_eq!(
        pairs,
        vec![
            ("vm-a".to_string(), "main".to_string()),
            ("vm-a".to_string(), "dev".to_string()),
            ("vm-b".to_string(), "build".to_string()),
        ]
    );
    assert!(plan.warnings.is_empty());
}

/// Invalid VM names are refused by the planner, not passed to a spawn.
#[test]
fn test_plan_restore_rejects_invalid_vm_name() {
    let plan = crate::restore_helpers::plan_restore(&sessions(&[("vm; rm -rf /", &["main:1"])]));
    assert!(plan.targets.is_empty());
    assert_eq!(plan.warnings.len(), 1);
}

/// The per-VM session cap is applied in the plan, so the dry-run preview shows
/// exactly what a real run would open — no more.
#[test]
fn test_plan_restore_applies_session_cap() {
    let many: Vec<String> = (0..30).map(|i| format!("s{}:1", i)).collect();
    let mut map = std::collections::HashMap::new();
    map.insert("vm-a".to_string(), many);
    let plan = crate::restore_helpers::plan_restore(&map);
    assert_eq!(
        plan.targets.len(),
        crate::cmd_list_data::MAX_SESSIONS_PER_VM
    );
    assert!(plan.warnings.iter().any(|w| w.contains("limiting")));
}

/// The dry-run report names every session and states plainly that nothing was
/// restored. `--dry-run` output must never read like a run that acted.
#[test]
fn test_dry_run_preview_states_nothing_was_restored() {
    let plan = crate::restore_helpers::plan_restore(&sessions(&[("vm-a", &["main:1", "dev:0"])]));
    let preview = crate::restore_helpers::format_dry_run_preview(&plan);
    assert!(preview.contains("vm-a"));
    assert!(preview.contains("main"));
    assert!(preview.contains("dev"));
    assert!(preview.contains("Would restore 2 session(s)"), "{preview}");
    assert!(preview.contains("Nothing was restored"), "{preview}");
    // Every line is marked, so a scrollback grep cannot mistake it for a run.
    for line in preview.lines().filter(|l| !l.trim().is_empty()) {
        assert!(line.contains("[dry-run]"), "unmarked line: {line}");
    }
}

/// An empty dry run still says nothing was restored rather than printing nothing.
#[test]
fn test_dry_run_preview_empty_plan() {
    let plan = crate::restore_helpers::plan_restore(&sessions(&[]));
    let preview = crate::restore_helpers::format_dry_run_preview(&plan);
    assert!(preview.contains("Would restore 0 session(s)"));
    assert!(preview.contains("Nothing was restored"));
}

/// `--no-multi-tab` must override the configured restore mode with one window
/// per session; without it the configured mode is left alone.
#[test]
fn test_no_multi_tab_forces_window_mode() {
    use azlin_core::RestoreMode;
    for configured in [RestoreMode::Auto, RestoreMode::Tab, RestoreMode::Window] {
        assert_eq!(
            crate::restore_helpers::effective_restore_mode(&configured, false),
            RestoreMode::Window,
            "--no-multi-tab must win over configured {configured}"
        );
        assert_eq!(
            crate::restore_helpers::effective_restore_mode(&configured, true),
            configured,
            "without --no-multi-tab the configured mode must be untouched"
        );
    }
}

/// Windows Terminal must actually be asked for a new window in that mode —
/// the flag has to reach the spawned command line, not just a variable.
#[test]
fn test_no_multi_tab_reaches_windows_terminal_args() {
    use azlin_core::RestoreMode;
    let windowed = crate::restore_helpers::effective_restore_mode(&RestoreMode::Tab, false);
    let args = crate::cmd_list_data::build_wt_restore_args("", "azlin", "vm-a", "main", &windowed);
    assert_eq!(args[0], "-w");
    assert_eq!(args[1], "new", "expected a new window, got {args:?}");

    let tabbed = crate::restore_helpers::effective_restore_mode(&RestoreMode::Tab, true);
    let args = crate::cmd_list_data::build_wt_restore_args("", "azlin", "vm-a", "main", &tabbed);
    assert_eq!(args[1], "0", "expected a tab in the current window");
}

/// `restore --dry-run` reaches the handler and fails gracefully without Azure.
#[test]
fn test_restore_dry_run_graceful_error_no_auth() {
    assert_graceful_auth_error(&["restore", "--dry-run"]);
}

// ═══════════════════════════════════════════════════════════════════════
// 3. batch stop --no-deallocate
// ═══════════════════════════════════════════════════════════════════════

/// `--no-deallocate` must run `az vm stop`, not `az vm deallocate`.
#[test]
fn test_batch_stop_no_deallocate_uses_stop() {
    assert_eq!(crate::batch_helpers::batch_stop_action(true), "stop");
}

/// Without the flag the VM is still deallocated (unchanged default).
#[test]
fn test_batch_stop_default_still_deallocates() {
    assert_eq!(crate::batch_helpers::batch_stop_action(false), "deallocate");
}

/// The batch path and the single-VM path (`azlin stop`) must agree about what
/// `--no-deallocate` means; they silently disagreed before this fix.
#[test]
fn test_batch_and_single_vm_stop_agree_on_no_deallocate() {
    for no_deallocate in [true, false] {
        // Single-VM path: `effective_deallocate = deallocate && !no_deallocate`.
        let effective_deallocate = !no_deallocate;
        let (single_label, _) = crate::stop_helpers::stop_action_labels(effective_deallocate);
        let batch_action = crate::batch_helpers::batch_stop_action(no_deallocate);
        let agree = match batch_action {
            "stop" => single_label == "Stopping",
            "deallocate" => single_label == "Deallocating",
            other => panic!("unexpected az action {other}"),
        };
        assert!(
            agree,
            "batch says '{batch_action}' but single-VM says '{single_label}' for \
             no_deallocate={no_deallocate}"
        );
    }
}

/// The action string is passed straight to `az vm <action> --ids`.
#[test]
fn test_batch_stop_action_builds_az_stop_args() {
    let action = crate::batch_helpers::batch_stop_action(true);
    let args = crate::batch_helpers::build_batch_args(action, &["/id/one"]);
    assert_eq!(args, vec!["vm", "stop", "--ids", "/id/one"]);
}

// ═══════════════════════════════════════════════════════════════════════
// 4. batch --vm-pattern / --all
// ═══════════════════════════════════════════════════════════════════════

/// A prefix glob selects only what it names — production must not match.
#[test]
fn test_glob_match_is_anchored() {
    assert!(crate::batch_helpers::glob_match("scratch-*", "scratch-01"));
    assert!(crate::batch_helpers::glob_match("scratch-*", "scratch-"));
    assert!(!crate::batch_helpers::glob_match(
        "scratch-*",
        "prod-scratch-01"
    ));
    assert!(!crate::batch_helpers::glob_match("scratch-*", "prod-db"));
}

#[test]
fn test_glob_match_wildcards() {
    assert!(crate::batch_helpers::glob_match("*", "anything"));
    assert!(crate::batch_helpers::glob_match("*-prod", "web-prod"));
    assert!(crate::batch_helpers::glob_match("vm-?", "vm-1"));
    assert!(!crate::batch_helpers::glob_match("vm-?", "vm-12"));
    assert!(crate::batch_helpers::glob_match("a*b*c", "azzbzzc"));
    assert!(!crate::batch_helpers::glob_match("a*b*c", "azzbzz"));
    assert!(crate::batch_helpers::glob_match("SCRATCH-*", "scratch-9"));
}

/// An empty pattern matches nothing rather than everything.
#[test]
fn test_glob_match_empty_pattern_matches_nothing_real() {
    assert!(!crate::batch_helpers::glob_match("", "vm-1"));
}

fn id_names() -> (Vec<String>, std::collections::HashMap<String, String>) {
    let ids = vec![
        "/subscriptions/s/rg/vm/scratch-01".to_string(),
        "/subscriptions/s/rg/vm/scratch-02".to_string(),
        "/subscriptions/s/rg/vm/prod-db".to_string(),
        "/subscriptions/s/rg/vm/unknown".to_string(),
    ];
    let mut names = std::collections::HashMap::new();
    names.insert(ids[0].clone(), "scratch-01".to_string());
    names.insert(ids[1].clone(), "scratch-02".to_string());
    names.insert(ids[2].clone(), "prod-db".to_string());
    // ids[3] deliberately has no name entry.
    (ids, names)
}

/// The whole point of the fix: the pattern actually removes VMs from the batch.
#[test]
fn test_filter_ids_by_pattern_excludes_production() {
    let (ids, names) = id_names();
    let filtered = crate::batch_helpers::filter_ids_by_pattern(&ids, &names, "scratch-*");
    assert_eq!(filtered.len(), 2);
    assert!(filtered.iter().all(|id| id.contains("scratch-")));
    assert!(
        !filtered.iter().any(|id| id.contains("prod-db")),
        "production VM survived the filter: {filtered:?}"
    );
}

/// An id whose name we do not know is dropped, not kept.
#[test]
fn test_filter_ids_by_pattern_drops_unnamed_ids() {
    let (ids, names) = id_names();
    let filtered = crate::batch_helpers::filter_ids_by_pattern(&ids, &names, "*");
    assert_eq!(filtered.len(), 3);
    assert!(!filtered.iter().any(|id| id.ends_with("unknown")));
}

/// A pattern that matches nothing yields nothing — never a fall-through to all.
#[test]
fn test_filter_ids_by_pattern_no_match_is_empty() {
    let (ids, names) = id_names();
    let filtered = crate::batch_helpers::filter_ids_by_pattern(&ids, &names, "nope-*");
    assert!(filtered.is_empty());
}

#[test]
fn test_validate_selection_rejects_all_with_filter() {
    let err = crate::batch_helpers::validate_selection(true, None, Some("scratch-*")).unwrap_err();
    assert!(err.contains("--all cannot be combined"), "{err}");
    assert!(crate::batch_helpers::validate_selection(true, Some("env=dev"), None).is_err());
}

#[test]
fn test_validate_selection_rejects_empty_pattern() {
    let err = crate::batch_helpers::validate_selection(false, None, Some("  ")).unwrap_err();
    assert!(err.contains("must not be empty"), "{err}");
}

#[test]
fn test_validate_selection_accepts_single_selectors() {
    assert!(crate::batch_helpers::validate_selection(true, None, None).is_ok());
    assert!(crate::batch_helpers::validate_selection(false, None, Some("scratch-*")).is_ok());
    assert!(crate::batch_helpers::validate_selection(false, Some("env=dev"), None).is_ok());
    assert!(crate::batch_helpers::validate_selection(false, None, None).is_ok());
}

/// The prompt must state that no filter is in effect. The old wording,
/// "Stop VMs matching 'all'", read as "all the matching ones".
#[test]
fn test_prompt_never_calls_an_absent_filter_innocuous() {
    let selection = crate::batch_helpers::describe_selection(None, None);
    let prompt = crate::batch_helpers::build_confirmation_prompt(
        "Stop and deallocate",
        &selection,
        "rg-prod",
    );
    assert!(prompt.contains("EVERY VM"), "{prompt}");
    assert!(!prompt.contains("matching 'all'"), "{prompt}");
    assert!(prompt.contains("rg-prod"));
}

/// A real filter is quoted back to the user verbatim.
#[test]
fn test_prompt_shows_the_actual_filter() {
    let selection = crate::batch_helpers::describe_selection(None, Some("scratch-*"));
    let prompt = crate::batch_helpers::build_confirmation_prompt("Stop", &selection, "rg-prod");
    assert!(prompt.contains("scratch-*"), "{prompt}");
    let both = crate::batch_helpers::describe_selection(Some("env=dev"), Some("scratch-*"));
    assert!(
        both.contains("env=dev") && both.contains("scratch-*"),
        "{both}"
    );
}

/// An empty result names the filter, so "nothing happened" is explicable.
#[test]
fn test_no_match_message_names_the_filter() {
    let msg = crate::batch_helpers::format_no_match_message("rg-prod", None, Some("scratch-*"));
    assert!(msg.contains("scratch-*"), "{msg}");
    assert!(msg.contains("rg-prod"));
    // Unfiltered keeps the original wording.
    assert_eq!(
        crate::batch_helpers::format_no_match_message("rg-prod", None, None),
        "No VMs found in resource group 'rg-prod'"
    );
}

#[test]
fn test_no_running_match_message_names_the_filter() {
    let msg = crate::batch_helpers::format_no_running_match_message("rg-prod", Some("scratch-*"));
    assert!(msg.contains("scratch-*"), "{msg}");
    assert_eq!(
        crate::batch_helpers::format_no_running_match_message("rg-prod", None),
        "No running VMs found in resource group 'rg-prod'"
    );
}

// ── End-to-end: the flags now reach the handler ───────────────────────
//
// These prove the flags are read rather than dropped: validation rejects the
// combination before any Azure call, which is only possible if the handler
// destructures them.

#[test]
fn test_batch_stop_rejects_all_with_vm_pattern() {
    let dir = TempDir::new().unwrap();
    let out = run_isolated(
        &dir,
        &[
            "batch",
            "stop",
            "--all",
            "--vm-pattern",
            "scratch-*",
            "--yes",
        ],
    );
    let combined = format!(
        "{}{}",
        String::from_utf8_lossy(&out.stdout),
        String::from_utf8_lossy(&out.stderr)
    );
    assert!(!out.status.success(), "should have failed: {combined}");
    assert!(combined.contains("--all cannot be combined"), "{combined}");
}

#[test]
fn test_batch_stop_rejects_empty_vm_pattern() {
    let dir = TempDir::new().unwrap();
    let out = run_isolated(&dir, &["batch", "stop", "--vm-pattern", "", "--yes"]);
    let combined = format!(
        "{}{}",
        String::from_utf8_lossy(&out.stdout),
        String::from_utf8_lossy(&out.stderr)
    );
    assert!(!out.status.success(), "should have failed: {combined}");
    assert!(combined.contains("must not be empty"), "{combined}");
}

#[test]
fn test_batch_start_rejects_all_with_vm_pattern() {
    let dir = TempDir::new().unwrap();
    let out = run_isolated(
        &dir,
        &["batch", "start", "--all", "--vm-pattern", "s-*", "--yes"],
    );
    let combined = format!(
        "{}{}",
        String::from_utf8_lossy(&out.stdout),
        String::from_utf8_lossy(&out.stderr)
    );
    assert!(!out.status.success(), "should have failed: {combined}");
    assert!(combined.contains("--all cannot be combined"), "{combined}");
}
