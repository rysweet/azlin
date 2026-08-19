use super::common::*;

/// Autopilot lifecycle, against an isolated `$HOME`.
///
/// `autopilot` resolves `autopilot.toml` from `dirs::home_dir()` and ignores
/// `AZLIN_CONFIG_DIR`, so this runs as a subprocess with `$HOME` redirected.
/// The previous version deleted the developer's real `~/.azlin/autopilot.toml`
/// and restored it best-effort at the end — leaving it destroyed whenever an
/// assertion in between failed (issue #1079).
#[tokio::test]
async fn test_dispatch_autopilot_full_lifecycle() {
    let dir = tempfile::TempDir::new().unwrap();
    std::fs::create_dir_all(dir.path().join(".azlin")).unwrap();

    // Status and config-show with no file present.
    assert_isolated_ok(
        &run_isolated_home(&dir, &["autopilot", "status"]),
        "status (unconfigured)",
    );
    assert_isolated_ok(
        &run_isolated_home(&dir, &["autopilot", "config", "--show"]),
        "config --show (no file)",
    );
    assert_isolated_ok(
        &run_isolated_home(&dir, &["autopilot", "config", "--set", "test_key=test_val"]),
        "config --set (creates file)",
    );

    assert_isolated_ok(
        &run_isolated_home(
            &dir,
            &[
                "autopilot",
                "enable",
                "--strategy",
                "aggressive",
                "--idle-threshold",
                "15",
                "--cpu-threshold",
                "5",
            ],
        ),
        "enable",
    );
    assert_isolated_ok(
        &run_isolated_home(&dir, &["autopilot", "status"]),
        "status (enabled)",
    );
    assert_isolated_ok(
        &run_isolated_home(&dir, &["autopilot", "config", "--show"]),
        "config --show (enabled)",
    );
    assert_isolated_ok(
        &run_isolated_home(&dir, &["autopilot", "config", "--set", "max_vms=10"]),
        "config --set max_vms",
    );

    assert_isolated_ok(
        &run_isolated_home(&dir, &["autopilot", "disable", "--keep-config"]),
        "disable --keep-config",
    );
    assert_isolated_ok(
        &run_isolated_home(&dir, &["autopilot", "status"]),
        "status (disabled)",
    );

    assert_isolated_ok(
        &run_isolated_home(
            &dir,
            &[
                "autopilot",
                "enable",
                "--budget",
                "100",
                "--strategy",
                "conservative",
            ],
        ),
        "enable with budget",
    );
    assert_isolated_ok(
        &run_isolated_home(&dir, &["autopilot", "disable"]),
        "disable",
    );
}

/// `config set` round-trip, against an isolated config dir.
///
/// This deliberately does not use `run_dispatch`: that would read and write the
/// developer's real `~/.azlin/config.toml` (see [`run_isolated`] and issue
/// #1079). Because the config under test is a throwaway temp dir, there is also
/// nothing to save and restore — the previous version of this test set the
/// region, asserted, then set it back, which silently left the real config
/// modified whenever the assertion in between failed.
#[tokio::test]
async fn test_dispatch_config_set_and_restore() {
    use azlin_core::AzlinConfig;
    let dir = tempfile::TempDir::new().unwrap();

    let out = run_isolated(&dir, &["config", "set", "default_region", "northeurope"]);
    assert_isolated_ok(&out, "config set default_region");

    // The write must land in the isolated dir, never in $HOME/.azlin.
    let written = dir.path().join("config.toml");
    assert!(
        written.is_file(),
        "config set must write into AZLIN_CONFIG_DIR, found nothing at {}",
        written.display()
    );

    let updated = AzlinConfig::load_from(&written).unwrap();
    assert_eq!(updated.default_region, "northeurope");
}

/// Isolation guard for #1079: config writes must not escape `AZLIN_CONFIG_DIR`.
///
/// Asserts the property directly rather than trusting convention, so a future
/// change that reintroduces an in-process `config set` against the real home
/// fails here instead of silently corrupting a developer's config.
#[tokio::test]
async fn test_config_writes_stay_inside_the_isolated_dir() {
    let dir = tempfile::TempDir::new().unwrap();
    let real = azlin_core::AzlinConfig::config_path().unwrap();
    let real_before = std::fs::read(&real).ok();

    let out = run_isolated(&dir, &["config", "set", "default_region", "westus2"]);
    assert_isolated_ok(&out, "config set default_region");

    assert!(
        dir.path().join("config.toml").is_file(),
        "the isolated config dir must receive the write"
    );
    assert_eq!(
        std::fs::read(&real).ok(),
        real_before,
        "an isolated `config set` must not modify the real config at {}",
        real.display()
    );
}

#[tokio::test]
async fn test_dispatch_config_set_unknown_key() {
    let r = run_dispatch(&["config", "set", "nonexistent_key_xyz", "value"]).await;
    assert!(r.is_err());
}

/// `session` set/get/clear round-trip, against an isolated config dir.
///
/// `session <vm> <name>` persists into the `[session_names]` table of the same
/// config file as `config set`, so running it in-process mutates the real
/// `~/.azlin/config.toml` and races other config-writing tests (issue #1079).
#[tokio::test]
async fn test_dispatch_session_set_get_clear() {
    let dir = tempfile::TempDir::new().unwrap();

    let out = run_isolated(&dir, &["session", "test-vm-cov", "my-session"]);
    assert_isolated_ok(&out, "session set");

    let out = run_isolated(&dir, &["session", "test-vm-cov"]);
    assert_isolated_ok(&out, "session get");
    assert!(
        String::from_utf8_lossy(&out.stdout).contains("my-session"),
        "session get must report the name just set, got: {}",
        String::from_utf8_lossy(&out.stdout)
    );

    let out = run_isolated(&dir, &["session", "test-vm-cov", "--clear"]);
    assert_isolated_ok(&out, "session clear");

    let out = run_isolated(&dir, &["session", "test-vm-cov"]);
    assert_isolated_ok(&out, "session get after clear");
}

#[tokio::test]
async fn test_dispatch_template_list_json() {
    let r = run_dispatch(&["--output", "json", "template", "list"]).await;
    assert!(r.is_ok());
}

#[tokio::test]
async fn test_dispatch_template_list_csv() {
    let r = run_dispatch(&["--output", "csv", "template", "list"]).await;
    assert!(r.is_ok());
}

#[tokio::test]
async fn test_dispatch_sessions_list_json() {
    let r = run_dispatch(&["--output", "json", "sessions", "list"]).await;
    assert!(r.is_ok());
}

#[tokio::test]
async fn test_dispatch_context_list_json() {
    let r = run_dispatch(&["--output", "json", "context", "list"]).await;
    assert!(r.is_ok());
}

#[tokio::test]
async fn test_dispatch_verbose_version() {
    let r = run_dispatch(&["--verbose", "version"]).await;
    assert!(r.is_ok());
}
