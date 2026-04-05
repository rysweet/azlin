#[test]
fn test_build_effective_remote_command_for_chromium() {
    let remote_command = vec!["chromium-browser".to_string(), "--no-sandbox".to_string()];
    let wrapped = crate::cmd_connect::build_effective_remote_command(true, &remote_command);

    assert_eq!(wrapped.len(), 1);
    assert!(wrapped[0].contains("snap list chromium >/dev/null 2>&1"));
    assert!(wrapped[0].contains("systemctl --user show-environment >/dev/null 2>&1"));
    assert!(
        wrapped[0].contains("azlin: snap Chromium detected but systemd-run --user is unavailable")
    );
    assert!(wrapped[0].contains(
        "then exec systemd-run --user --scope --quiet -- 'chromium-browser' '--no-sandbox';"
    ));
    assert!(wrapped[0].contains("exec 'chromium-browser' '--no-sandbox'; fi"));
}

#[test]
fn test_build_effective_remote_command_wraps_env_prefixed_chromium() {
    let remote_command = vec![
        "env".to_string(),
        "GTK_THEME=Adwaita".to_string(),
        "chromium-browser".to_string(),
        "--no-sandbox".to_string(),
    ];
    let wrapped = crate::cmd_connect::build_effective_remote_command(true, &remote_command);

    assert_eq!(wrapped.len(), 1);
    assert!(wrapped[0].contains(
        "then exec systemd-run --user --scope --quiet -- 'env' 'GTK_THEME=Adwaita' 'chromium-browser' '--no-sandbox';"
    ));
    assert!(wrapped[0].contains("'env' 'GTK_THEME=Adwaita' 'chromium-browser' '--no-sandbox'; fi"));
}

#[test]
fn test_build_effective_remote_command_wraps_bare_env_assignment_chromium() {
    let remote_command = vec![
        "FOO=1".to_string(),
        "chromium-browser".to_string(),
        "--no-sandbox".to_string(),
    ];
    let wrapped = crate::cmd_connect::build_effective_remote_command(true, &remote_command);

    assert_eq!(wrapped.len(), 1);
    assert!(wrapped[0].contains("FOO=1"));
    assert!(wrapped[0].contains(
        "then exec systemd-run --user --scope --quiet -- 'env' 'FOO=1' 'chromium-browser' '--no-sandbox';"
    ));
}

#[test]
fn test_build_effective_remote_command_wraps_env_option_prefixed_chromium() {
    let remote_command = vec![
        "env".to_string(),
        "-u".to_string(),
        "DISPLAY".to_string(),
        "chromium-browser".to_string(),
        "--no-sandbox".to_string(),
    ];
    let wrapped = crate::cmd_connect::build_effective_remote_command(true, &remote_command);

    assert_eq!(wrapped.len(), 1);
    assert!(wrapped[0].contains(
        "then exec systemd-run --user --scope --quiet -- 'env' '-u' 'DISPLAY' 'chromium-browser' '--no-sandbox';"
    ));
}

#[test]
fn test_build_effective_remote_command_wraps_env_split_string_chromium() {
    let remote_command = vec![
        "env".to_string(),
        "-S".to_string(),
        "chromium-browser --no-sandbox".to_string(),
    ];
    let wrapped = crate::cmd_connect::build_effective_remote_command(true, &remote_command);

    assert_eq!(wrapped.len(), 1);
    assert!(wrapped[0].contains(
        "then exec systemd-run --user --scope --quiet -- 'env' '-S' 'chromium-browser --no-sandbox';"
    ));
}

#[test]
fn test_build_effective_remote_command_wraps_env_terminator_chromium() {
    let remote_command = vec![
        "env".to_string(),
        "--".to_string(),
        "chromium-browser".to_string(),
        "--no-sandbox".to_string(),
    ];
    let wrapped = crate::cmd_connect::build_effective_remote_command(true, &remote_command);

    assert_eq!(wrapped.len(), 1);
    assert!(wrapped[0].contains(
        "then exec systemd-run --user --scope --quiet -- 'env' '--' 'chromium-browser' '--no-sandbox';"
    ));
}

#[test]
fn test_build_effective_remote_command_wraps_env_terminator_assignment_prefixed_chromium() {
    let remote_command = vec![
        "env".to_string(),
        "--".to_string(),
        "FOO=1".to_string(),
        "chromium-browser".to_string(),
        "--no-sandbox".to_string(),
    ];
    let wrapped = crate::cmd_connect::build_effective_remote_command(true, &remote_command);

    assert_eq!(wrapped.len(), 1);
    assert!(wrapped[0].contains(
        "then exec systemd-run --user --scope --quiet -- 'env' '--' 'FOO=1' 'chromium-browser' '--no-sandbox';"
    ));
}

#[test]
fn test_build_effective_remote_command_executes_bare_env_assignment() {
    use std::fs;
    use std::os::unix::fs::PermissionsExt;
    use std::process::Command;
    use std::time::{SystemTime, UNIX_EPOCH};

    let unique = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .expect("clock should be after epoch")
        .as_nanos();
    let temp_dir = std::env::temp_dir().join(format!(
        "azlin-bare-env-command-{}-{}",
        std::process::id(),
        unique
    ));
    fs::create_dir_all(&temp_dir).expect("create temp dir");

    let snap_path = temp_dir.join("snap");
    let chromium_path = temp_dir.join("chromium-browser");
    let output_path = temp_dir.join("bare-env-output.txt");

    fs::write(&snap_path, "#!/bin/sh\nexit 1\n").expect("write snap stub");
    fs::write(
        &chromium_path,
        format!(
            "#!/bin/sh\nprintf '%s' \"$FOO\" > {}\n",
            output_path.display()
        ),
    )
    .expect("write chromium stub");

    fs::set_permissions(&snap_path, fs::Permissions::from_mode(0o755)).expect("chmod snap stub");
    fs::set_permissions(&chromium_path, fs::Permissions::from_mode(0o755))
        .expect("chmod chromium stub");

    let remote_command = vec![
        "FOO=1".to_string(),
        "chromium-browser".to_string(),
        output_path.display().to_string(),
    ];
    let wrapped = crate::cmd_connect::build_effective_remote_command(true, &remote_command);
    let path = format!(
        "{}:{}",
        temp_dir.display(),
        std::env::var("PATH").unwrap_or_default()
    );
    let status = Command::new("sh")
        .arg("-lc")
        .arg(&wrapped[0])
        .env("PATH", path)
        .status()
        .expect("execute wrapped shell command");

    assert!(
        status.success(),
        "wrapped command should execute successfully"
    );
    assert_eq!(
        fs::read_to_string(&output_path).expect("read output"),
        "1",
        "bare env assignment should reach chromium stub via env"
    );

    let _ = fs::remove_dir_all(&temp_dir);
}

#[test]
fn test_build_effective_remote_command_skips_non_browser_apps() {
    let remote_command = vec!["gimp".to_string()];
    let wrapped = crate::cmd_connect::build_effective_remote_command(true, &remote_command);
    assert_eq!(wrapped, remote_command);
}

#[test]
fn test_build_effective_remote_command_requires_x11() {
    let remote_command = vec!["chromium-browser".to_string()];
    let wrapped = crate::cmd_connect::build_effective_remote_command(false, &remote_command);
    assert_eq!(wrapped, remote_command);
}

#[test]
fn test_maybe_wrap_vnc_app_command_for_chromium() {
    let wrapped =
        crate::gui_launch_helpers::maybe_wrap_vnc_app_command("chromium-browser --no-sandbox");
    assert!(wrapped.contains("snap list chromium >/dev/null 2>&1"));
    assert!(wrapped.contains("azlin: snap Chromium detected but systemd-run --user is unavailable"));
    assert!(wrapped.contains(
        "then systemd-run --user --scope --quiet -- sh -lc 'chromium-browser --no-sandbox';"
    ));
    assert!(wrapped.contains("sh -lc 'chromium-browser --no-sandbox'; fi"));
}

#[test]
fn test_maybe_wrap_vnc_app_command_handles_quoted_program_name() {
    let wrapped =
        crate::gui_launch_helpers::maybe_wrap_vnc_app_command("\"chromium-browser\" --no-sandbox");
    assert!(wrapped.contains(
        "then systemd-run --user --scope --quiet -- sh -lc '\"chromium-browser\" --no-sandbox';"
    ));
    assert!(wrapped.contains("sh -lc '\"chromium-browser\" --no-sandbox'; fi"));
}

#[test]
fn test_maybe_wrap_vnc_app_command_handles_env_prefixed_chromium() {
    let wrapped = crate::gui_launch_helpers::maybe_wrap_vnc_app_command(
        "FOO=1 chromium-browser --no-sandbox",
    );
    assert!(wrapped.contains(
        "then systemd-run --user --scope --quiet -- sh -lc 'FOO=1 chromium-browser --no-sandbox';"
    ));
    assert!(wrapped.contains("sh -lc 'FOO=1 chromium-browser --no-sandbox'; fi"));
}

#[test]
fn test_maybe_wrap_vnc_app_command_handles_env_option_prefixed_chromium() {
    let wrapped = crate::gui_launch_helpers::maybe_wrap_vnc_app_command(
        "env -i chromium-browser --no-sandbox",
    );
    assert!(wrapped.contains(
        "then systemd-run --user --scope --quiet -- sh -lc 'env -i chromium-browser --no-sandbox';"
    ));
    assert!(wrapped.contains("sh -lc 'env -i chromium-browser --no-sandbox'; fi"));
}

#[test]
fn test_maybe_wrap_vnc_app_command_handles_env_split_string_chromium() {
    let wrapped = crate::gui_launch_helpers::maybe_wrap_vnc_app_command(
        "env -S 'chromium-browser --no-sandbox'",
    );
    assert!(wrapped.contains("systemd-run --user --scope --quiet -- sh -lc"));
    assert!(wrapped.contains("chromium-browser --no-sandbox"));
}

#[test]
fn test_maybe_wrap_vnc_app_command_handles_env_terminator_chromium() {
    let wrapped = crate::gui_launch_helpers::maybe_wrap_vnc_app_command(
        "env -- chromium-browser --no-sandbox",
    );
    assert!(wrapped.contains("systemd-run --user --scope --quiet -- sh -lc"));
    assert!(wrapped.contains("env -- chromium-browser --no-sandbox"));
}

#[test]
fn test_maybe_wrap_vnc_app_command_handles_env_terminator_assignment_prefixed_chromium() {
    let wrapped = crate::gui_launch_helpers::maybe_wrap_vnc_app_command(
        "env -- FOO=1 chromium-browser --no-sandbox",
    );
    assert!(wrapped.contains("systemd-run --user --scope --quiet -- sh -lc"));
    assert!(wrapped.contains("env -- FOO=1 chromium-browser --no-sandbox"));
}

#[test]
fn test_maybe_wrap_vnc_app_command_handles_env_terminator_quoted_assignment_prefixed_chromium() {
    let wrapped = crate::gui_launch_helpers::maybe_wrap_vnc_app_command(
        "env -- FOO='two words' chromium-browser --no-sandbox",
    );
    assert!(wrapped.contains("systemd-run --user --scope --quiet -- sh -lc"));
    assert!(wrapped.contains("env --"));
    assert!(wrapped.contains("chromium-browser --no-sandbox"));
    assert!(wrapped.contains("two words"));
}

#[test]
fn test_maybe_wrap_vnc_app_command_handles_quoted_env_assignment_value() {
    let wrapped = crate::gui_launch_helpers::maybe_wrap_vnc_app_command(
        "FOO='two words' chromium-browser --no-sandbox",
    );
    assert!(wrapped.contains("systemd-run --user --scope --quiet -- sh -lc"));
    assert!(wrapped.contains("chromium-browser --no-sandbox"));
    assert!(wrapped.contains("two words"));
}

#[test]
fn test_maybe_wrap_vnc_app_command_leaves_other_apps_unchanged() {
    let wrapped = crate::gui_launch_helpers::maybe_wrap_vnc_app_command("gimp");
    assert_eq!(wrapped, "gimp");
}

#[test]
fn test_build_effective_remote_command_shell_escapes_spaces() {
    let remote_command = vec![
        "chromium-browser".to_string(),
        "--user-data-dir=/tmp/test dir".to_string(),
    ];
    let wrapped = crate::cmd_connect::build_effective_remote_command(true, &remote_command);

    assert_eq!(wrapped.len(), 1);
    assert!(wrapped[0].contains(
        "then exec systemd-run --user --scope --quiet -- 'chromium-browser' '--user-data-dir=/tmp/test dir';"
    ));
    assert!(wrapped[0].contains("'chromium-browser' '--user-data-dir=/tmp/test dir'; fi"));
}
