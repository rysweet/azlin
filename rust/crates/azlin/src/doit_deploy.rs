//! What `azlin doit deploy`'s three discarded flags mean.
//!
//! `--output-dir`, `--max-iterations` and `--quiet` were accepted and dropped
//! (#1089). The command asks the model for a list of `az` commands, prints
//! them, and runs them — so all three name real properties of that run, and
//! `--max-iterations` names the one that matters most: nothing bounded how
//! many commands a model could hand back to be executed against a live
//! subscription.

use anyhow::{Context, Result};
use std::path::{Path, PathBuf};

/// The `az` commands in a generated plan, in order.
///
/// The model is asked for one command per line; anything else it says — prose,
/// fences, blank lines — is not a command and is skipped, exactly as the
/// executor already did.
pub fn plan_commands(plan: &str) -> Vec<&str> {
    plan.lines()
        .map(str::trim)
        .filter(|line| line.starts_with("az "))
        .collect()
}

/// Whether a plan asks for more commands than `--max-iterations` allows.
///
/// Returns the message to show, or `None` if the plan fits. A plan that
/// overruns is refused rather than truncated: running the first 50 of 80
/// commands leaves the subscription in a state neither the user nor the model
/// intended, and half a deployment is worse than none.
pub fn over_iteration_limit(command_count: usize, max_iterations: u32) -> Option<String> {
    if max_iterations == 0 || command_count <= max_iterations as usize {
        return None;
    }
    Some(format!(
        "The plan has {} commands, over the {} allowed by --max-iterations. Nothing has run. \
         Raise --max-iterations, use --max-iterations 0 for no limit, or narrow the request.",
        command_count, max_iterations
    ))
}

/// Where a run's artifacts go, created if needed.
///
/// `--output-dir` promised "Output directory for generated artifacts" for a
/// command that wrote no artifacts at all: the plan scrolled past and the
/// output of every command it ran went to the terminal and nowhere else.
pub fn prepare_output_dir(dir: &Path) -> Result<()> {
    std::fs::create_dir_all(dir)
        .with_context(|| format!("Could not create --output-dir {}", dir.display()))
}

/// The file a plan is written to.
pub fn plan_path(dir: &Path) -> PathBuf {
    dir.join("plan.txt")
}

/// The file a run's transcript is written to.
pub fn transcript_path(dir: &Path) -> PathBuf {
    dir.join("transcript.txt")
}

/// One line of transcript for a command that ran.
pub fn transcript_line(command: &str, exit_code: Option<i32>) -> String {
    match exit_code {
        Some(0) => format!("ok    {}\n", command),
        Some(code) => format!("fail({}) {}\n", code, command),
        // A command killed by a signal has no exit code, and reporting that as
        // success is how a failed deployment looks like a clean one.
        None => format!("fail(signal) {}\n", command),
    }
}

/// What `--quiet` suppresses.
///
/// Progress only. Errors, the refusal above, and the confirmation prompt are
/// not progress: a quiet flag that hides why a deployment stopped is worse
/// than a loud one.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Verbosity {
    quiet: bool,
}

impl Verbosity {
    pub fn new(quiet: bool) -> Self {
        Self { quiet }
    }

    /// The plan, the per-command echo, the closing summary.
    pub fn shows_progress(self) -> bool {
        !self.quiet
    }

    /// Failures, refusals, and anything the user must answer.
    pub fn shows_problems(self) -> bool {
        true
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    // ── plan_commands ────────────────────────────────────────────

    #[test]
    fn only_az_lines_count_as_commands() {
        let plan = "Here is the plan:\n\naz group create -n x\n```\naz vm create -n y\nDone.\n";
        assert_eq!(
            plan_commands(plan),
            vec!["az group create -n x", "az vm create -n y"]
        );
    }

    #[test]
    fn an_indented_command_still_counts() {
        assert_eq!(plan_commands("   az vm list\n"), vec!["az vm list"]);
    }

    // ── over_iteration_limit ─────────────────────────────────────

    #[test]
    fn a_plan_within_the_limit_runs() {
        assert_eq!(over_iteration_limit(50, 50), None);
        assert_eq!(over_iteration_limit(0, 50), None);
    }

    #[test]
    fn a_plan_over_the_limit_is_refused_whole_rather_than_truncated() {
        let msg = over_iteration_limit(80, 50).unwrap();
        assert!(msg.contains("80"), "{}", msg);
        assert!(msg.contains("50"), "{}", msg);
        assert!(
            msg.contains("Nothing has run"),
            "half a deployment is worse than none: {}",
            msg
        );
        assert!(msg.contains("--max-iterations 0"), "{}", msg);
    }

    #[test]
    fn zero_means_no_limit_as_it_does_on_every_other_azlin_flag() {
        assert_eq!(over_iteration_limit(10_000, 0), None);
    }

    // ── transcript ───────────────────────────────────────────────

    #[test]
    fn the_transcript_records_how_each_command_ended() {
        assert_eq!(transcript_line("az vm list", Some(0)), "ok    az vm list\n");
        assert_eq!(
            transcript_line("az vm list", Some(2)),
            "fail(2) az vm list\n"
        );
        assert_eq!(
            transcript_line("az vm list", None),
            "fail(signal) az vm list\n",
            "a command killed by a signal is not a success"
        );
    }

    #[test]
    fn artifacts_land_in_the_directory_the_user_named() {
        let dir = tempfile::TempDir::new().unwrap();
        let target = dir.path().join("nested/run");
        prepare_output_dir(&target).unwrap();
        assert!(target.is_dir());
        assert_eq!(plan_path(&target), target.join("plan.txt"));
        assert_eq!(transcript_path(&target), target.join("transcript.txt"));
    }

    // ── Verbosity ────────────────────────────────────────────────

    #[test]
    fn quiet_hides_progress_and_never_hides_problems() {
        let quiet = Verbosity::new(true);
        assert!(!quiet.shows_progress());
        assert!(
            quiet.shows_problems(),
            "a quiet flag that hides why a deployment stopped is worse than a loud one"
        );

        let loud = Verbosity::new(false);
        assert!(loud.shows_progress());
        assert!(loud.shows_problems());
    }
}
