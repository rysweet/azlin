/// Classify SSH result exit code into a status label and whether it succeeded.
pub fn classify_result(exit_code: i32) -> (&'static str, bool) {
    if exit_code == 0 {
        ("OK", true)
    } else {
        ("FAIL", false)
    }
}

/// Build the progress-bar finish message for a completed SSH execution.
pub fn finish_message(exit_code: i32, stdout: &str, stderr: &str) -> String {
    if exit_code == 0 {
        let line_count = stdout.trim().lines().count();
        format!("✓ done ({} lines)", line_count)
    } else {
        let err_summary = stderr.trim().lines().next().unwrap_or("error");
        format!("✗ {}", err_summary)
    }
}

/// Build the output-column text for the fleet summary table.
pub fn format_output_text(exit_code: i32, stdout: &str, stderr: &str, show_output: bool) -> String {
    if show_output {
        let out = stdout.trim();
        if out.is_empty() {
            stderr.trim().to_string()
        } else {
            out.to_string()
        }
    } else if exit_code != 0 {
        stderr.trim().lines().next().unwrap_or("").to_string()
    } else {
        String::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    // -- classify_result --

    #[test]
    fn classify_ok() {
        let (label, ok) = classify_result(0);
        assert_eq!(label, "OK");
        assert!(ok);
    }

    #[test]
    fn classify_fail_nonzero() {
        let (label, ok) = classify_result(1);
        assert_eq!(label, "FAIL");
        assert!(!ok);
    }

    #[test]
    fn classify_fail_negative() {
        let (label, ok) = classify_result(-1);
        assert_eq!(label, "FAIL");
        assert!(!ok);
    }

    // -- finish_message --

    #[test]
    fn finish_success_counts_lines() {
        let msg = finish_message(0, "line1\nline2\nline3\n", "");
        assert!(msg.contains("3 lines"));
        assert!(msg.starts_with('\u{2713}')); // checkmark
    }

    #[test]
    fn finish_success_empty_output() {
        let msg = finish_message(0, "", "");
        assert!(msg.contains("0 lines"));
    }

    #[test]
    fn finish_failure_shows_first_stderr_line() {
        let msg = finish_message(1, "", "first error\nsecond error\n");
        assert!(msg.contains("first error"));
        assert!(!msg.contains("second error"));
    }

    #[test]
    fn finish_failure_fallback_error() {
        let msg = finish_message(1, "", "");
        assert!(msg.contains("error"));
    }

    // -- format_output_text --

    #[test]
    fn output_show_prefers_stdout() {
        let text = format_output_text(0, "hello\n", "err\n", true);
        assert_eq!(text, "hello");
    }

    #[test]
    fn output_show_falls_back_to_stderr() {
        let text = format_output_text(0, "  \n", "fallback\n", true);
        assert_eq!(text, "fallback");
    }

    #[test]
    fn output_hide_success_empty() {
        let text = format_output_text(0, "output", "err", false);
        assert_eq!(text, "");
    }

    #[test]
    fn output_hide_failure_shows_first_stderr() {
        let text = format_output_text(1, "", "first line\nsecond\n", false);
        assert_eq!(text, "first line");
    }

    #[test]
    fn output_hide_failure_empty_stderr() {
        let text = format_output_text(1, "", "", false);
        assert_eq!(text, "");
    }
}
