//! Wording for the `azlin list` filter disclosure (#1142).
//!
//! `azlin list` hides VMs that are not running. That default is right. The
//! defect was that it was *silent*: a resource group holding six VMs printed
//! `Total: 2 VMs | 2 running` and gave no hint that four more existed, or that
//! their attached Premium SSD was billing at full rate the whole time. This
//! module owns the one copy of the text that fixes that, so the table footer,
//! the JSON run and the CSV run cannot drift apart.
//!
//! Everything here is pure: no I/O, no colour, no `println!`. The renderers
//! decide where the strings go and how they are styled.
//!
//! **The disclosure is counts, never identities.** These functions take a
//! [`FilterCounts`] and nothing else, so they structurally cannot name a hidden
//! VM, echo a tag value, or repeat the pattern you supplied. That is deliberate:
//! `--tag` and `--vm-pattern` are how you *narrow* a listing before pasting it
//! into an issue or a chat channel, and printing the excluded names back into
//! the footer would undo the narrowing you asked for. To see the names, run the
//! listing that includes them.

use crate::list_helpers::FilterCounts;

/// The remedy for hidden non-running VMs.
///
/// Deliberately ASCII-only -- no em dash, no backticks, straight quotes around
/// the command -- so it survives a non-UTF-8 terminal and a naive `grep -F`.
///
/// It names `--all`, never `-a`. `-a` is `--show-all-vms`, which scans every
/// *resource group* and is still running-only; sending an operator there would
/// reproduce the original blind spot somewhere new.
pub const HIDDEN_REMEDY: &str =
    "Hidden VMs still bill for attached storage. Run 'azlin list --all' to include them.";

/// One clause per filter stage that removed something, in the order the stages
/// ran. Empty when nothing was removed.
fn clauses(counts: &FilterCounts) -> Vec<String> {
    let mut out = Vec::new();
    if counts.hidden_not_running > 0 {
        // "hidden" rather than "excluded": these rows were removed by a default
        // the operator never asked for, which is a different thing from a
        // filter they typed. The parenthetical says which states qualify,
        // because "not running" alone reads as "broken" rather than "costing
        // you money while switched off".
        out.push(format!(
            "{} hidden (stopped/deallocated)",
            counts.hidden_not_running
        ));
    }
    if counts.dropped_by_tag > 0 {
        out.push(format!("{} excluded by --tag", counts.dropped_by_tag));
    }
    if counts.dropped_by_pattern > 0 {
        out.push(format!(
            "{} excluded by --vm-pattern",
            counts.dropped_by_pattern
        ));
    }
    out
}

/// Text appended to the table's `Total: N VMs | M running` footer.
///
/// Empty when nothing was filtered, so an unfiltered listing prints exactly
/// what it printed before. The clauses extend the existing ` | `-separated
/// summary rather than starting a new line, because that footer is the line an
/// operator actually reads, and it is the line that lied.
pub fn summary_suffix(counts: &FilterCounts) -> String {
    clauses(counts)
        .iter()
        .map(|c| format!(" | {c}"))
        .collect::<Vec<_>>()
        .join("")
}

/// The remedy line, when there is anything `--all` would actually reveal.
///
/// `None` when only `--tag`/`--vm-pattern` dropped rows: `--all` would not
/// bring those back, and pointing at it would be wrong advice.
pub fn remedy_line(counts: &FilterCounts) -> Option<&'static str> {
    (counts.hidden_not_running > 0).then_some(HIDDEN_REMEDY)
}

/// The disclosure as standalone lines, for the machine-readable formats.
///
/// `-o json` and `-o csv` have no summary footer to extend, and their stdout
/// belongs to the consumer -- prose written there would corrupt a payload being
/// piped into `jq` or Python's `csv`. So the same information goes to stderr,
/// where an operator at a terminal still reads it and a parser never sees it.
///
/// Empty when nothing was filtered: a diagnostic that fires on every run is
/// noise, and noise is what people learn to ignore.
pub fn stderr_lines(counts: &FilterCounts) -> Vec<String> {
    if !counts.any() {
        return Vec::new();
    }
    let mut lines = vec![format!("Note: {}.", clauses(counts).join(", "))];
    if let Some(remedy) = remedy_line(counts) {
        lines.push(remedy.to_string());
    }
    lines
}

#[cfg(test)]
mod tests {
    use super::*;

    fn counts(hidden: usize, tag: usize, pattern: usize) -> FilterCounts {
        FilterCounts {
            hidden_not_running: hidden,
            dropped_by_tag: tag,
            dropped_by_pattern: pattern,
        }
    }

    #[test]
    fn silent_counts_produce_no_text_at_all() {
        let c = FilterCounts::default();
        assert_eq!(summary_suffix(&c), "");
        assert_eq!(remedy_line(&c), None);
        assert!(stderr_lines(&c).is_empty());
    }

    #[test]
    fn hidden_clause_names_the_count_and_the_states() {
        // The exact substrings the CLI-level tests grep for. The incident was
        // that neither reached the screen.
        let suffix = summary_suffix(&counts(4, 0, 0));
        assert_eq!(suffix, " | 4 hidden (stopped/deallocated)");
        assert!(suffix.contains("4 hidden"));
        assert!(suffix.contains("stopped/deallocated"));
    }

    #[test]
    fn remedy_names_all_and_never_the_short_flag() {
        let remedy = remedy_line(&counts(1, 0, 0)).expect("hidden VMs have a remedy");
        assert!(remedy.contains("azlin list --all"));
        assert!(
            !remedy.contains("list -a"),
            "-a is --show-all-vms, a different flag: {remedy}"
        );
        assert!(
            remedy.is_ascii(),
            "the remedy must survive a non-UTF-8 terminal: {remedy}"
        );
    }

    #[test]
    fn tag_and_pattern_drops_get_their_own_clauses() {
        assert_eq!(summary_suffix(&counts(0, 3, 0)), " | 3 excluded by --tag");
        assert_eq!(
            summary_suffix(&counts(0, 0, 2)),
            " | 2 excluded by --vm-pattern"
        );
    }

    #[test]
    fn tag_only_drops_offer_no_remedy() {
        // `--all` reveals nothing the tag filter removed, so advising it would
        // send the operator to a listing that is still missing their rows.
        assert_eq!(remedy_line(&counts(0, 3, 0)), None);
        assert_eq!(remedy_line(&counts(0, 0, 2)), None);
        assert_eq!(
            stderr_lines(&counts(0, 3, 0)),
            ["Note: 3 excluded by --tag."]
        );
    }

    #[test]
    fn clauses_appear_in_stage_order() {
        assert_eq!(
            summary_suffix(&counts(4, 3, 2)),
            " | 4 hidden (stopped/deallocated) | 3 excluded by --tag \
             | 2 excluded by --vm-pattern"
        );
    }

    #[test]
    fn stderr_lines_carry_the_counts_and_the_remedy() {
        let lines = stderr_lines(&counts(4, 0, 2));
        assert_eq!(
            lines,
            [
                "Note: 4 hidden (stopped/deallocated), 2 excluded by --vm-pattern.",
                HIDDEN_REMEDY,
            ]
        );
    }

    #[test]
    fn stderr_lines_never_leak_a_name_or_a_filter_value() {
        // Enforced by the signature -- these functions cannot see a VmInfo or
        // the raw --tag/--vm-pattern strings. This test pins the consequence so
        // a future refactor that widens the signature has to argue with it.
        for line in stderr_lines(&counts(9, 9, 9)) {
            assert!(line.is_ascii(), "unexpected non-ASCII: {line}");
            assert!(!line.contains('='), "no tag value may appear: {line}");
            assert!(!line.contains('*'), "no pattern may appear: {line}");
        }
    }
}
