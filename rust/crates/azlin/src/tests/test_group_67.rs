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
    assert!(wrapped[0].contains("then exec systemd-run --user --scope --quiet --"));
    assert!(wrapped[0].contains("'chromium-browser' '--no-sandbox';"));
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
