use crate::shell_escape;

const SNAP_CHROMIUM_PROBE: &str =
    "command -v snap >/dev/null 2>&1 && snap list chromium >/dev/null 2>&1";
const USER_SYSTEMD_PROBE: &str =
    "command -v systemd-run >/dev/null 2>&1 && command -v systemctl >/dev/null 2>&1 && systemctl --user show-environment >/dev/null 2>&1";

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

fn leading_remote_command_program(remote_command: &[String]) -> Option<&str> {
    let mut args = remote_command.iter().map(String::as_str);
    let mut saw_env = false;

    while let Some(arg) = args.next() {
        if arg == "env" {
            saw_env = true;
            continue;
        }
        if saw_env && is_env_assignment(arg) {
            continue;
        }
        return Some(arg);
    }

    None
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

    loop {
        let (word, rest) = split_first_shell_word(remainder)?;
        remainder = rest;
        if word == "env" || is_env_assignment(&word) {
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
    format!(
        "if {snap_probe} && {systemd_probe}; then exec systemd-run --user --scope --quiet -- {command}; else exec {command}; fi",
        snap_probe = SNAP_CHROMIUM_PROBE,
        systemd_probe = USER_SYSTEMD_PROBE,
        command = command
    )
}

fn build_conditional_scoped_vnc_command(command: &str) -> String {
    format!(
        "if {snap_probe} && {systemd_probe}; then systemd-run --user --scope --quiet -- {command}; else {command}; fi",
        snap_probe = SNAP_CHROMIUM_PROBE,
        systemd_probe = USER_SYSTEMD_PROBE,
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

    let escaped_args = remote_command
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
