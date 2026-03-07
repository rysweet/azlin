use crate::*;
use std::fs;
use tempfile::TempDir;

// ── env_helpers tests ────────────────────────────────────────

#[test]
fn test_split_env_var_valid() {
    let (k, v) = crate::env_helpers::split_env_var("FOO=bar").unwrap();
    assert_eq!(k, "FOO");
    assert_eq!(v, "bar");
}

#[test]
fn test_split_env_var_value_with_equals() {
    let (k, v) = crate::env_helpers::split_env_var("DSN=postgres://u:p@h/db?opt=1").unwrap();
    assert_eq!(k, "DSN");
    assert_eq!(v, "postgres://u:p@h/db?opt=1");
}

#[test]
fn test_split_env_var_empty_value() {
    let (k, v) = crate::env_helpers::split_env_var("EMPTY=").unwrap();
    assert_eq!(k, "EMPTY");
    assert_eq!(v, "");
}

#[test]
fn test_split_env_var_no_equals() {
    assert!(crate::env_helpers::split_env_var("NO_EQUALS").is_none());
}

#[test]
fn test_split_env_var_leading_equals() {
    assert!(crate::env_helpers::split_env_var("=value").is_none());
}

#[test]
fn test_build_env_set_cmd_contains_key_value() {
    let cmd = crate::env_helpers::build_env_set_cmd("MY_KEY", "'my_val'");
    assert!(cmd.contains("MY_KEY"));
    assert!(cmd.contains("'my_val'"));
    assert!(cmd.contains("grep -q"));
    assert!(cmd.contains("~/.profile"));
}

#[test]
fn test_build_env_delete_cmd() {
    let cmd = crate::env_helpers::build_env_delete_cmd("OLD_VAR");
    assert!(cmd.contains("OLD_VAR"));
    assert!(cmd.contains("sed -i"));
    assert!(cmd.contains("~/.profile"));
}

#[test]
fn test_env_list_cmd() {
    assert_eq!(crate::env_helpers::env_list_cmd(), "env | sort");
}

#[test]
fn test_env_clear_cmd() {
    let cmd = crate::env_helpers::env_clear_cmd();
    assert!(cmd.contains("sed -i"));
    assert!(cmd.contains("export"));
}

#[test]
fn test_parse_env_output_basic() {
    let output = "HOME=/root\nPATH=/usr/bin\nSHELL=/bin/bash\n";
    let vars = crate::env_helpers::parse_env_output(output);
    assert_eq!(vars.len(), 3);
    assert_eq!(vars[0], ("HOME".into(), "/root".into()));
    assert_eq!(vars[1], ("PATH".into(), "/usr/bin".into()));
}

#[test]
fn test_parse_env_output_empty() {
    assert!(crate::env_helpers::parse_env_output("").is_empty());
}

#[test]
fn test_parse_env_output_value_with_equals() {
    let output = "DSN=host=localhost dbname=test\n";
    let vars = crate::env_helpers::parse_env_output(output);
    assert_eq!(vars.len(), 1);
    assert_eq!(vars[0].0, "DSN");
    assert_eq!(vars[0].1, "host=localhost dbname=test");
}

#[test]
fn test_build_env_file() {
    let vars = vec![("A".into(), "1".into()), ("B".into(), "two".into())];
    let file = crate::env_helpers::build_env_file(&vars);
    assert_eq!(file, "A=1\nB=two");
}

#[test]
fn test_build_env_file_empty() {
    assert_eq!(crate::env_helpers::build_env_file(&[]), "");
}

#[test]
fn test_parse_env_file_basic() {
    let content = "FOO=bar\n# comment\n\nBAZ=qux\n";
    let vars = crate::env_helpers::parse_env_file(content);
    assert_eq!(vars.len(), 2);
    assert_eq!(vars[0], ("FOO".into(), "bar".into()));
    assert_eq!(vars[1], ("BAZ".into(), "qux".into()));
}

#[test]
fn test_parse_env_file_empty_lines_only() {
    assert!(crate::env_helpers::parse_env_file("\n\n  \n").is_empty());
}

#[test]
fn test_parse_env_file_comments_only() {
    assert!(crate::env_helpers::parse_env_file("# comment\n# another").is_empty());
}

#[test]
fn test_parse_env_file_whitespace_trimming() {
    let content = "  KEY=value  \n  OTHER=val2  \n";
    let vars = crate::env_helpers::parse_env_file(content);
    assert_eq!(vars.len(), 2);
    assert_eq!(vars[0].0, "KEY");
    assert_eq!(vars[0].1, "value"); // line is trimmed, value after = is as-is
}

#[test]
fn test_parse_env_file_roundtrip() {
    let original = vec![
        ("X".into(), "10".into()),
        ("Y".into(), "hello world".into()),
    ];
    let file = crate::env_helpers::build_env_file(&original);
    let parsed = crate::env_helpers::parse_env_file(&file);
    assert_eq!(parsed, original);
}

// ── sync_helpers tests ───────────────────────────────────────

#[test]
fn test_default_dotfiles_has_expected_entries() {
    let files = crate::sync_helpers::default_dotfiles();
    assert!(files.contains(&".bashrc"));
    assert!(files.contains(&".profile"));
    assert!(files.contains(&".vimrc"));
    assert!(files.contains(&".gitconfig"));
    assert!(files.contains(&".tmux.conf"));
    assert_eq!(files.len(), 5);
}

#[test]
fn test_build_rsync_args_structure() {
    let args = crate::sync_helpers::build_rsync_args(
        "/home/me/.bashrc",
        "azureuser",
        "10.0.0.1",
        ".bashrc",
    );
    assert_eq!(args[0], "-az");
    assert_eq!(args[1], "-e");
    assert_eq!(args[2], "ssh -o StrictHostKeyChecking=accept-new");
    assert_eq!(args[3], "/home/me/.bashrc");
    assert_eq!(args[4], "azureuser@10.0.0.1:~/.bashrc");
}

#[test]
fn test_build_rsync_args_special_chars_in_ip() {
    let args = crate::sync_helpers::build_rsync_args("/tmp/f", "user", "192.168.1.100", ".vimrc");
    assert!(args[4].contains("192.168.1.100"));
}

// ── health_helpers tests ─────────────────────────────────────

#[test]
fn test_metric_color_green() {
    assert_eq!(crate::health_helpers::metric_color(0.0), "green");
    assert_eq!(crate::health_helpers::metric_color(50.0), "green");
}

#[test]
fn test_metric_color_yellow() {
    assert_eq!(crate::health_helpers::metric_color(50.1), "yellow");
    assert_eq!(crate::health_helpers::metric_color(80.0), "yellow");
}

#[test]
fn test_metric_color_red() {
    assert_eq!(crate::health_helpers::metric_color(80.1), "red");
    assert_eq!(crate::health_helpers::metric_color(100.0), "red");
}

#[test]
fn test_state_color_running() {
    assert_eq!(crate::health_helpers::state_color("running"), "green");
}

#[test]
fn test_state_color_stopped_deallocated() {
    assert_eq!(crate::health_helpers::state_color("stopped"), "red");
    assert_eq!(crate::health_helpers::state_color("deallocated"), "red");
}

#[test]
fn test_state_color_unknown() {
    assert_eq!(crate::health_helpers::state_color("starting"), "yellow");
    assert_eq!(crate::health_helpers::state_color(""), "yellow");
}

#[test]
fn test_format_percentage() {
    assert_eq!(crate::health_helpers::format_percentage(0.0), "0.0%");
    assert_eq!(crate::health_helpers::format_percentage(99.95), "99.9%");
    assert_eq!(crate::health_helpers::format_percentage(42.567), "42.6%");
}

#[test]
fn test_status_emoji_green() {
    assert_eq!(crate::health_helpers::status_emoji(10.0, 20.0, 30.0), "🟢");
    assert_eq!(crate::health_helpers::status_emoji(70.0, 70.0, 70.0), "🟢");
}

#[test]
fn test_status_emoji_yellow() {
    assert_eq!(crate::health_helpers::status_emoji(70.1, 10.0, 10.0), "🟡");
    assert_eq!(crate::health_helpers::status_emoji(10.0, 70.1, 10.0), "🟡");
    assert_eq!(crate::health_helpers::status_emoji(10.0, 10.0, 70.1), "🟡");
}

#[test]
fn test_status_emoji_red() {
    assert_eq!(crate::health_helpers::status_emoji(90.1, 10.0, 10.0), "🔴");
    assert_eq!(crate::health_helpers::status_emoji(10.0, 90.1, 10.0), "🔴");
    assert_eq!(crate::health_helpers::status_emoji(10.0, 10.0, 90.1), "🔴");
}

#[test]
fn test_status_emoji_boundary() {
    // exactly 90.0 is yellow, not red
    assert_eq!(crate::health_helpers::status_emoji(90.0, 90.0, 90.0), "🟡");
}
