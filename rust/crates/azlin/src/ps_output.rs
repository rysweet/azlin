//! How `azlin ps` lays out the output of several VMs.
//!
//! `--grouped` reads "Group output by VM instead of prefixing", so the help
//! has always described two layouts. Only one was ever built: every run
//! printed a `── vm ──` header and a block, whether the flag was passed or not
//! (#1089). The flag changed nothing, and the prefixed layout it names as the
//! alternative did not exist.
//!
//! Prefixed is the default the flag's own text implies, and is the layout that
//! makes `azlin ps | grep node` answer "which VM is running node" — the
//! question a fleet-wide `ps` is asked. `--grouped` selects what every run
//! printed before, unchanged to the character.

/// One VM's output with its name on every line.
///
/// Names are padded to a common width so the process columns stay aligned
/// across VMs. A width of zero means no prefix at all: `azlin ps --vm web-1`
/// would otherwise stamp a name the user just typed onto all twenty lines,
/// which is noise, and people run that form — scripts run the fleet-wide one.
pub fn prefix_lines(vm_name: &str, output: &str, name_width: usize) -> String {
    use std::fmt::Write as _;

    if name_width == 0 {
        // Still normalised to exactly one newline per line of input.
        let mut out = String::with_capacity(output.len() + 1);
        for line in output.lines() {
            out.push_str(line);
            out.push('\n');
        }
        return out;
    }

    let mut out = String::with_capacity(output.len() + output.lines().count() * (name_width + 2));
    for line in output.lines() {
        // `write!` into the buffer rather than a `format!` per line: this is a
        // fleet command, so the line count is however many VMs times twenty.
        let _ = writeln!(out, "{:<width$}  {}", vm_name, line, width = name_width);
    }
    out
}

/// The width to pad VM names to, given every VM in this run.
///
/// Zero for a single VM — see [`prefix_lines`] — and the longest name
/// otherwise, so one long name does not misalign the rest.
pub fn name_width(vm_names: &[String]) -> usize {
    if vm_names.len() < 2 {
        return 0;
    }
    vm_names
        .iter()
        .map(|n| n.chars().count())
        .max()
        .unwrap_or(0)
}

/// The header that opens a VM's block in the grouped layout.
pub fn group_header(vm_name: &str) -> String {
    format!("── {} ──", vm_name)
}

/// A VM that answered nothing at all.
///
/// An empty block under a header is readable; an empty *prefixed* section is
/// indistinguishable from the VM having been skipped, so it says so.
pub fn empty_note(vm_name: &str, grouped: bool, name_width: usize) -> String {
    if grouped || name_width == 0 {
        "  (no output)\n".to_string()
    } else {
        format!("{:<width$}  (no output)\n", vm_name, width = name_width)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn every_line_carries_the_vm_name() {
        let out = prefix_lines("web-1", "root 1 init\nroot 2 node\n", 5);
        assert_eq!(out, "web-1  root 1 init\nweb-1  root 2 node\n");
    }

    #[test]
    fn names_are_padded_so_the_columns_still_line_up() {
        let width = name_width(&["a".to_string(), "web-longer".to_string()]);
        assert_eq!(width, 10);
        let short = prefix_lines("a", "x\n", width);
        let long = prefix_lines("web-longer", "x\n", width);
        let col = |s: &str| s.find('x').unwrap();
        assert_eq!(col(&short), col(&long), "{:?} vs {:?}", short, long);
    }

    #[test]
    fn output_without_a_trailing_newline_still_ends_with_one() {
        let out = prefix_lines("vm", "last line", 2);
        assert!(out.ends_with('\n'), "{:?}", out);
        assert_eq!(out.lines().count(), 1);
    }

    #[test]
    fn a_single_vm_is_not_prefixed_with_the_name_the_user_just_typed() {
        // `azlin ps --vm web-1` would otherwise stamp "web-1" onto all twenty
        // lines. People run that form; scripts run the fleet-wide one.
        let width = name_width(&["only".to_string()]);
        assert_eq!(width, 0);
        assert_eq!(prefix_lines("only", "x\ny\n", width), "x\ny\n");
    }

    #[test]
    fn two_vms_are_both_prefixed() {
        let names = vec!["a".to_string(), "b".to_string()];
        let width = name_width(&names);
        assert!(width > 0);
        assert!(prefix_lines("a", "x\n", width).starts_with('a'));
    }

    #[test]
    fn empty_output_says_so_rather_than_vanishing() {
        assert_eq!(empty_note("web-1", false, 5), "web-1  (no output)\n");
        assert_eq!(empty_note("web-1", true, 5), "  (no output)\n");
        // A single VM carries no prefix here either, for the same reason.
        assert_eq!(empty_note("web-1", false, 0), "  (no output)\n");
    }

    #[test]
    fn the_grouped_header_is_unchanged_from_what_every_run_printed_before() {
        assert_eq!(group_header("web-1"), "── web-1 ──");
    }
}
