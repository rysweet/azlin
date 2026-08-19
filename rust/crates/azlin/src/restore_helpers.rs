//! Pure planning helpers for `azlin restore`.
//!
//! Expanding the collected tmux sessions into the exact list of connections
//! that *would* be made is the whole content of `--dry-run`, so it lives here,
//! separated from the terminal-spawning side effects, and can be asserted
//! without an Azure subscription.

use std::collections::HashMap;

/// One session to reconnect to.
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct RestoreTarget {
    pub vm: String,
    pub session: String,
}

/// The full set of connections a restore would make, plus the warnings the
/// caller should surface for input that was skipped or capped.
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub(crate) struct RestorePlan {
    pub targets: Vec<RestoreTarget>,
    pub warnings: Vec<String>,
}

/// Expand collected tmux sessions into the ordered list of connections.
///
/// VM names are validated and sessions parsed with the same helpers the real
/// restore path uses, and the per-VM cap is applied here, so a `--dry-run`
/// preview cannot drift from what a real run would do. Output is sorted by VM
/// name because the input is a `HashMap`.
pub(crate) fn plan_restore(tmux_sessions: &HashMap<String, Vec<String>>) -> RestorePlan {
    let mut plan = RestorePlan::default();
    let mut vm_names: Vec<&String> = tmux_sessions.keys().collect();
    vm_names.sort();

    for vm_name in vm_names {
        let sessions = &tmux_sessions[vm_name];
        if !crate::cmd_list_data::is_valid_restore_vm_name(vm_name) {
            plan.warnings.push("skipping VM with invalid name".into());
            continue;
        }
        if sessions.len() > crate::cmd_list_data::MAX_SESSIONS_PER_VM {
            plan.warnings.push(format!(
                "limiting {} to {} sessions (found {})",
                vm_name,
                crate::cmd_list_data::MAX_SESSIONS_PER_VM,
                sessions.len()
            ));
        }
        for raw in sessions
            .iter()
            .take(crate::cmd_list_data::MAX_SESSIONS_PER_VM)
        {
            match crate::cmd_list_data::parse_session_name(raw) {
                Some(session) => plan.targets.push(RestoreTarget {
                    vm: vm_name.clone(),
                    session,
                }),
                None => plan
                    .warnings
                    .push(format!("skipping invalid session name for {}", vm_name)),
            }
        }
    }
    plan
}

/// Render the `--dry-run` preview.
///
/// Every line is prefixed `[dry-run]` and the report ends by stating plainly
/// that nothing was restored, so the output can never be mistaken for a run
/// that acted.
pub(crate) fn format_dry_run_preview(plan: &RestorePlan) -> String {
    let mut out = String::new();
    out.push_str(&format!(
        "\n[dry-run] Would restore {} session(s):\n",
        plan.targets.len()
    ));
    for t in &plan.targets {
        out.push_str(&format!(
            "  [dry-run] Would connect to {} (session: {})\n",
            t.vm, t.session
        ));
    }
    out.push_str("[dry-run] Nothing was restored; no terminal sessions were opened.");
    out
}

/// Resolve the restore mode actually used, honouring `--no-multi-tab`.
///
/// `multi_tab` is false when the user passed `--no-multi-tab`, which asks for
/// one window per session instead of one tab per session in the current window.
/// That is exactly [`RestoreMode::Window`], so the flag overrides the
/// configured `restore_mode` rather than introducing a parallel notion.
///
/// On Linux and macOS azlin already opens a separate window per session, so the
/// override only changes behaviour under Windows Terminal, where the tab/window
/// distinction exists.
pub(crate) fn effective_restore_mode(
    configured: &azlin_core::RestoreMode,
    multi_tab: bool,
) -> azlin_core::RestoreMode {
    if multi_tab {
        configured.clone()
    } else {
        azlin_core::RestoreMode::Window
    }
}
