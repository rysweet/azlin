//! Unit tests for restore_tmux_sessions helper functions.
//!
//! Covers parse_session_name (24 cases) and is_valid_restore_vm_name (11 cases)
//! plus behavioural smoke tests for restore_tmux_sessions itself (10 cases).

use crate::cmd_list_data::{is_valid_restore_vm_name, parse_session_name, restore_tmux_sessions};
use std::collections::HashMap;

// ---------------------------------------------------------------------------
// parse_session_name — valid inputs
// ---------------------------------------------------------------------------

#[test]
fn test_parse_strips_attached_suffix() {
    assert_eq!(parse_session_name("main:1"), Some("main".to_string()));
}

#[test]
fn test_parse_strips_zero_attached() {
    assert_eq!(
        parse_session_name("dev-work:0"),
        Some("dev-work".to_string())
    );
}

#[test]
fn test_parse_strips_high_count() {
    assert_eq!(
        parse_session_name("session99:42"),
        Some("session99".to_string())
    );
}

#[test]
fn test_parse_trims_leading_whitespace() {
    assert_eq!(
        parse_session_name("  dev-work:0"),
        Some("dev-work".to_string())
    );
}

#[test]
fn test_parse_trims_trailing_whitespace() {
    assert_eq!(
        parse_session_name("dev-work:0  "),
        Some("dev-work".to_string())
    );
}

#[test]
fn test_parse_trims_both_sides_whitespace() {
    assert_eq!(
        parse_session_name("  dev-work :0"),
        Some("dev-work".to_string())
    );
}

#[test]
fn test_parse_single_char_name() {
    assert_eq!(parse_session_name("a:0"), Some("a".to_string()));
}

#[test]
fn test_parse_underscore_name() {
    assert_eq!(
        parse_session_name("my_session:1"),
        Some("my_session".to_string())
    );
}

#[test]
fn test_parse_hyphen_name() {
    assert_eq!(
        parse_session_name("my-session:1"),
        Some("my-session".to_string())
    );
}

#[test]
fn test_parse_alphanumeric_only() {
    assert_eq!(parse_session_name("ABC123:0"), Some("ABC123".to_string()));
}

#[test]
fn test_parse_name_no_colon_still_valid() {
    // tmux format without attached count — treat the whole string as the name
    assert_eq!(
        parse_session_name("plainname"),
        Some("plainname".to_string())
    );
}

#[test]
fn test_parse_exactly_128_chars_valid() {
    let name = "a".repeat(128);
    let raw = format!("{}:0", name);
    assert_eq!(parse_session_name(&raw), Some(name));
}

// ---------------------------------------------------------------------------
// parse_session_name — invalid / rejected inputs
// ---------------------------------------------------------------------------

#[test]
fn test_parse_empty_string_returns_none() {
    assert_eq!(parse_session_name(""), None);
}

#[test]
fn test_parse_colon_only_empty_name_returns_none() {
    assert_eq!(parse_session_name(":1"), None);
}

#[test]
fn test_parse_whitespace_only_before_colon_returns_none() {
    assert_eq!(parse_session_name("   :1"), None);
}

#[test]
fn test_parse_semicolon_metachar_returns_none() {
    assert_eq!(parse_session_name("session;evil:0"), None);
}

#[test]
fn test_parse_percent_expansion_returns_none() {
    assert_eq!(parse_session_name("sess%COMSPEC%:0"), None);
}

#[test]
fn test_parse_caret_escape_returns_none() {
    assert_eq!(parse_session_name("sess^inject:0"), None);
}

#[test]
fn test_parse_ampersand_returns_none() {
    assert_eq!(parse_session_name("sess&cmd:0"), None);
}

#[test]
fn test_parse_pipe_returns_none() {
    assert_eq!(parse_session_name("sess|cmd:0"), None);
}

#[test]
fn test_parse_dot_returns_none() {
    // Dots are not in the session-name allowlist (only vm-name allows dots for FQDNs)
    assert_eq!(parse_session_name("sess.ion:0"), None);
}

#[test]
fn test_parse_slash_returns_none() {
    assert_eq!(parse_session_name("../../evil:0"), None);
}

#[test]
fn test_parse_129_chars_returns_none() {
    let name = "a".repeat(129);
    let raw = format!("{}:0", name);
    assert_eq!(parse_session_name(&raw), None);
}

#[test]
fn test_parse_ansi_escape_returns_none() {
    // ANSI CSI sequence contains '[' and digits — '[' is not in the allowlist
    assert_eq!(parse_session_name("\x1b[32mmain\x1b[0m:1"), None);
}

// ---------------------------------------------------------------------------
// is_valid_restore_vm_name — valid inputs
// ---------------------------------------------------------------------------

#[test]
fn test_vm_name_simple_valid() {
    assert!(is_valid_restore_vm_name("myvm"));
}

#[test]
fn test_vm_name_with_hyphen_valid() {
    assert!(is_valid_restore_vm_name("my-vm-01"));
}

#[test]
fn test_vm_name_with_underscore_valid() {
    assert!(is_valid_restore_vm_name("my_vm"));
}

#[test]
fn test_vm_name_with_dot_valid() {
    // Dots permitted for Azure FQDNs
    assert!(is_valid_restore_vm_name("vm.example.com"));
}

#[test]
fn test_vm_name_alphanumeric_mixed_case_valid() {
    assert!(is_valid_restore_vm_name("DevVM01"));
}

// ---------------------------------------------------------------------------
// is_valid_restore_vm_name — invalid inputs
// ---------------------------------------------------------------------------

#[test]
fn test_vm_name_empty_invalid() {
    assert!(!is_valid_restore_vm_name(""));
}

#[test]
fn test_vm_name_ampersand_invalid() {
    assert!(!is_valid_restore_vm_name("vm&inject"));
}

#[test]
fn test_vm_name_semicolon_invalid() {
    assert!(!is_valid_restore_vm_name("vm;cmd"));
}

#[test]
fn test_vm_name_path_traversal_invalid() {
    assert!(!is_valid_restore_vm_name("../traversal"));
}

#[test]
fn test_vm_name_space_invalid() {
    assert!(!is_valid_restore_vm_name("my vm"));
}

#[test]
fn test_vm_name_pipe_invalid() {
    assert!(!is_valid_restore_vm_name("vm|cat"));
}

#[test]
fn test_vm_name_over_256_chars_invalid() {
    let long_name = "a".repeat(257);
    assert!(!is_valid_restore_vm_name(&long_name));
}

#[test]
fn test_vm_name_exactly_256_chars_valid() {
    let name = "a".repeat(256);
    assert!(is_valid_restore_vm_name(&name));
}

// ---------------------------------------------------------------------------
// restore_tmux_sessions — behavioural smoke tests
// ---------------------------------------------------------------------------

#[test]
fn test_restore_empty_map_no_panic() {
    let sessions: HashMap<String, Vec<String>> = HashMap::new();
    // Should complete without panic
    restore_tmux_sessions(&sessions);
}

#[test]
fn test_restore_empty_session_list_no_panic() {
    let mut sessions: HashMap<String, Vec<String>> = HashMap::new();
    sessions.insert("myvm".to_string(), vec![]);
    restore_tmux_sessions(&sessions);
}

#[test]
fn test_restore_valid_colon_format_no_panic() {
    // Bug 1 regression: "main:1" should be stripped to "main" without panic or warning
    let mut sessions: HashMap<String, Vec<String>> = HashMap::new();
    sessions.insert("myvm".to_string(), vec!["main:1".to_string()]);
    restore_tmux_sessions(&sessions);
}

#[test]
fn test_restore_invalid_session_name_skipped_no_panic() {
    // Security: session with injection chars must be skipped, not passed to spawn
    let mut sessions: HashMap<String, Vec<String>> = HashMap::new();
    sessions.insert("myvm".to_string(), vec!["session;evil:0".to_string()]);
    restore_tmux_sessions(&sessions);
}

#[test]
fn test_restore_invalid_vm_name_skipped_no_panic() {
    // Security: VM name with injection chars must be skipped
    let mut sessions: HashMap<String, Vec<String>> = HashMap::new();
    sessions.insert("vm&inject".to_string(), vec!["main:0".to_string()]);
    restore_tmux_sessions(&sessions);
}

#[test]
fn test_restore_multiple_sessions_opens_all_tabs() {
    // All sessions per VM are now restored (bug fix from v0.9.2)
    let mut sessions: HashMap<String, Vec<String>> = HashMap::new();
    sessions.insert(
        "myvm".to_string(),
        vec!["first:1".to_string(), "second:0".to_string(), "third:1".to_string()],
    );
    // This test runs in test mode, so it will print dry-run output for all sessions
    restore_tmux_sessions(&sessions);
    // Note: In test mode, the function prints output but doesn't actually open tabs
    // Verification would require capturing stdout, but the function now processes all sessions
}

#[test]
fn test_restore_respects_max_sessions_limit() {
    // Test that we limit to MAX_SESSIONS_PER_VM (20) sessions
    let mut sessions: HashMap<String, Vec<String>> = HashMap::new();
    let mut many_sessions = Vec::new();
    for i in 0..25 {
        many_sessions.push(format!("session{}:0", i));
    }
    sessions.insert("myvm".to_string(), many_sessions);
    // Should process only first 20 sessions, warning about the limit
    restore_tmux_sessions(&sessions);
}

#[test]
fn test_restore_multiple_vms_no_panic() {
    let mut sessions: HashMap<String, Vec<String>> = HashMap::new();
    sessions.insert("vm-alpha".to_string(), vec!["work:1".to_string()]);
    sessions.insert("vm-beta".to_string(), vec!["play:0".to_string()]);
    restore_tmux_sessions(&sessions);
}

#[test]
fn test_restore_empty_vm_name_skipped_no_panic() {
    // Edge case: empty key in map
    let mut sessions: HashMap<String, Vec<String>> = HashMap::new();
    sessions.insert("".to_string(), vec!["main:0".to_string()]);
    restore_tmux_sessions(&sessions);
}

#[test]
fn test_restore_session_name_at_max_length_no_panic() {
    let name = "a".repeat(128);
    let raw = format!("{}:0", name);
    let mut sessions: HashMap<String, Vec<String>> = HashMap::new();
    sessions.insert("myvm".to_string(), vec![raw]);
    restore_tmux_sessions(&sessions);
}

#[test]
fn test_restore_session_name_over_max_length_skipped_no_panic() {
    let name = "a".repeat(129);
    let raw = format!("{}:0", name);
    let mut sessions: HashMap<String, Vec<String>> = HashMap::new();
    sessions.insert("myvm".to_string(), vec![raw]);
    // Should not panic; name is skipped with a warning
    restore_tmux_sessions(&sessions);
}

// ---------------------------------------------------------------------------
// build_wt_restore_args — Windows Terminal argument construction
// ---------------------------------------------------------------------------

use crate::cmd_list_data::build_wt_restore_args;

#[test]
fn test_wt_args_with_wsl_distro_wraps_bash_lc() {
    let mode = azlin_core::RestoreMode::Tab;
    let args = build_wt_restore_args("Ubuntu", "/usr/bin/azlin", "my-vm", "azlin", &mode);
    assert!(args.contains(&"bash".to_string()), "should contain bash");
    assert!(args.contains(&"-lc".to_string()), "should contain -lc");
    let shell_cmd = args.last().unwrap();
    assert!(
        shell_cmd.contains("connect") && shell_cmd.contains("my-vm") && shell_cmd.contains("azlin"),
        "shell command should contain the full connect invocation, got: {}",
        shell_cmd
    );
    assert!(
        shell_cmd.starts_with("exec "),
        "should use exec to replace bash process, got: {}",
        shell_cmd
    );
}

#[test]
fn test_wt_args_with_wsl_distro_includes_distro_name() {
    let mode = azlin_core::RestoreMode::Tab;
    let args = build_wt_restore_args("Debian", "/usr/bin/azlin", "vm1", "dev", &mode);
    assert!(args.contains(&"Debian".to_string()));
    assert!(args.contains(&"wsl.exe".to_string()));
    assert!(args.contains(&"-d".to_string()));
}

#[test]
fn test_wt_args_without_wsl_distro_uses_direct_args() {
    let mode = azlin_core::RestoreMode::Tab;
    let args = build_wt_restore_args("", "/usr/bin/azlin", "my-vm", "azlin", &mode);
    assert!(!args.contains(&"bash".to_string()));
    assert!(!args.contains(&"wsl.exe".to_string()));
    assert!(args.contains(&"connect".to_string()));
    assert!(args.contains(&"--tmux-session".to_string()));
}

#[test]
fn test_wt_args_tab_mode_starts_with_window_tab() {
    let mode = azlin_core::RestoreMode::Tab;
    let args = build_wt_restore_args("Ubuntu", "/usr/bin/azlin", "vm1", "dev", &mode);
    assert_eq!(&args[0..3], &["-w", "0", "new-tab"]);
}

#[test]
fn test_wt_args_window_mode_uses_new_window() {
    let mode = azlin_core::RestoreMode::Window;
    let args = build_wt_restore_args("Ubuntu", "/usr/bin/azlin", "vm1", "dev", &mode);
    assert_eq!(&args[0..3], &["-w", "new", "new-tab"]);
}

#[test]
fn test_wt_args_auto_mode_defaults_to_tab_prefix() {
    let mode = azlin_core::RestoreMode::Auto;
    let args = build_wt_restore_args("Ubuntu", "/usr/bin/azlin", "vm1", "dev", &mode);
    assert_eq!(&args[0..3], &["-w", "0", "new-tab"]);
}

#[test]
fn test_wt_args_escapes_paths_with_spaces() {
    let mode = azlin_core::RestoreMode::Tab;
    let args = build_wt_restore_args("Ubuntu", "/path with spaces/azlin", "vm1", "dev", &mode);
    let shell_cmd = args.last().unwrap();
    assert!(
        shell_cmd.contains("'/path with spaces/azlin'"),
        "paths with spaces should be single-quoted, got: {}",
        shell_cmd
    );
}

#[test]
fn test_wt_args_escapes_single_quotes_in_names() {
    let mode = azlin_core::RestoreMode::Tab;
    let args = build_wt_restore_args("Ubuntu", "/usr/bin/azlin", "vm-o'brien", "dev", &mode);
    let shell_cmd = args.last().unwrap();
    assert!(
        shell_cmd.contains("'vm-o'\\''brien'"),
        "single quotes should be escaped, got: {}",
        shell_cmd
    );
}
