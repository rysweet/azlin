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
