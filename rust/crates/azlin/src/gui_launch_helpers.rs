use crate::shell_escape;

const SNAP_CHROMIUM_PROBE: &str =
    "command -v snap >/dev/null 2>&1 && snap list chromium >/dev/null 2>&1";
const USER_SYSTEMD_PROBE: &str =
    "command -v systemd-run >/dev/null 2>&1 && command -v systemctl >/dev/null 2>&1 && systemctl --user show-environment >/dev/null 2>&1";
const SYSTEMD_RUN_WARNING: &str =
    "azlin: snap Chromium detected but systemd-run --user is unavailable; Chromium may still fail with the snap cgroup error. Retry from a login session or run systemd-run --user --scope chromium-browser --no-sandbox manually.";

fn is_snap_sensitive_browser_program(program: &str) -> bool {
    let trimmed = program.trim_matches(|c| c == '"' || c == '\'');
    let name = std::path::Path::new(trimmed)
        .file_name()
        .and_then(|value| value.to_str())
        .unwrap_or(trimmed);
    matches!(name, "chromium" | "chromium-browser")
}

fn is_env_assignment(word: &str) -> bool {
    matches!(word.split_once('='), Some((name, _)) if !name.is_empty())
}

fn is_env_flag(word: &str) -> bool {
    matches!(word, "-i" | "--ignore-environment" | "-0" | "--null")
        || word.starts_with("--unset=")
        || word.starts_with("--chdir=")
        || word.starts_with("--split-string=")
}

fn env_flag_takes_value(word: &str) -> bool {
    matches!(
        word,
        "-u" | "--unset" | "-C" | "--chdir" | "-S" | "--split-string"
    )
}

fn leading_remote_command_program(remote_command: &[String]) -> Option<&str> {
    let mut args = remote_command.iter().map(String::as_str);
    let mut saw_env = false;

    while let Some(arg) = args.next() {
        if arg == "env" {
            saw_env = true;
            continue;
        }
        if is_env_assignment(arg) {
            continue;
        }
        if saw_env && is_env_flag(arg) {
            continue;
        }
        if saw_env && env_flag_takes_value(arg) {
            let _ = args.next();
            continue;
        }
        return Some(arg);
    }

    None
}

fn normalize_remote_command_for_shell(remote_command: &[String]) -> Vec<String> {
    let leading_assignments = remote_command
        .iter()
        .take_while(|arg| is_env_assignment(arg))
        .count();

    if leading_assignments == 0 {
        return remote_command.to_vec();
    }

    let mut normalized = Vec::with_capacity(remote_command.len() + 1);
    normalized.push("env".to_string());
    normalized.extend(remote_command.iter().take(leading_assignments).cloned());
    normalized.extend(remote_command.iter().skip(leading_assignments).cloned());
    normalized
}

fn split_first_shell_word(command: &str) -> Option<(String, &str)> {
    let trimmed = command.trim_start();
    if trimmed.is_empty() {
        return None;
    }

    let mut chars = trimmed.char_indices();
    let (_, first) = chars.next()?;
    if first == '"' || first == '\'' {
        let quote = first;
        for (index, ch) in chars {
            if ch == quote {
                return Some((trimmed[1..index].to_string(), &trimmed[index + 1..]));
            }
        }
        return None;
    }

    let end = trimmed
        .char_indices()
        .find_map(|(index, ch)| {
            if ch.is_whitespace() || ";|&()<>".contains(ch) {
                Some(index)
            } else {
                None
            }
        })
        .unwrap_or(trimmed.len());
    Some((trimmed[..end].to_string(), &trimmed[end..]))
}

fn leading_shell_command_word(command: &str) -> Option<String> {
    let mut remainder = command;
    let mut saw_env = false;

    loop {
        let (word, rest) = split_first_shell_word(remainder)?;
        remainder = rest;
        if word == "env" {
            saw_env = true;
            continue;
        }
        if is_env_assignment(&word) {
            continue;
        }
        if saw_env && is_env_flag(&word) {
            continue;
        }
        if saw_env && env_flag_takes_value(&word) {
            let (_, rest_after_value) = split_first_shell_word(remainder)?;
            remainder = rest_after_value;
            continue;
        }
        return Some(word);
    }
}

fn is_snap_sensitive_browser_command(command: &str) -> bool {
    leading_shell_command_word(command)
        .map(|word| is_snap_sensitive_browser_program(&word))
        .unwrap_or(false)
}

fn build_conditional_scoped_x11_command(command: &str) -> String {
    let escaped_warning = shell_escape(SYSTEMD_RUN_WARNING);
    format!(
        "if {snap_probe}; then if {systemd_probe}; then exec systemd-run --user --scope --quiet -- {command}; else >&2 printf '%s\\n' {warning}; exec {command}; fi; else exec {command}; fi",
        snap_probe = SNAP_CHROMIUM_PROBE,
        systemd_probe = USER_SYSTEMD_PROBE,
        warning = escaped_warning,
        command = command
    )
}

fn build_conditional_scoped_vnc_command(command: &str) -> String {
    let escaped_warning = shell_escape(SYSTEMD_RUN_WARNING);
    format!(
        "if {snap_probe}; then if {systemd_probe}; then systemd-run --user --scope --quiet -- {command}; else >&2 printf '%s\\n' {warning}; {command}; fi; else {command}; fi",
        snap_probe = SNAP_CHROMIUM_PROBE,
        systemd_probe = USER_SYSTEMD_PROBE,
        warning = escaped_warning,
        command = command
    )
}

pub(crate) fn maybe_wrap_x11_remote_command(
    x11: bool,
    remote_command: &[String],
) -> Option<Vec<String>> {
    let Some(program) = leading_remote_command_program(remote_command) else {
        return None;
    };

    if !x11 || !is_snap_sensitive_browser_program(program) {
        return None;
    }

    let normalized_command = normalize_remote_command_for_shell(remote_command);
    let escaped_args = normalized_command
        .iter()
        .map(|arg| shell_escape(arg))
        .collect::<Vec<_>>()
        .join(" ");
    Some(vec![build_conditional_scoped_x11_command(&escaped_args)])
}

pub(crate) fn maybe_wrap_vnc_app_command(command: &str) -> String {
    if !is_snap_sensitive_browser_command(command) {
        return command.to_string();
    }

    let shell_command = format!("sh -lc {}", shell_escape(command));
    build_conditional_scoped_vnc_command(&shell_command)
}
