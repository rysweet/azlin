//! Regression tests for the `--config` half of #1089.
//!
//! `--config <path>` was declared on 60 subcommand variants and honoured by
//! exactly one (`azlin new`). Every other command called `AzlinConfig::load()`,
//! which resolves `$AZLIN_CONFIG_DIR/config.toml` or `~/.azlin/config.toml`, so
//! `azlin killall --config ./staging.toml --force` read the *default* config and
//! could delete every azlin VM in the wrong resource group while reporting
//! success.
//!
//! Everything here runs `azlin` as a subprocess with `AZLIN_CONFIG_DIR` pointed
//! at a temp dir, so no test touches the developer's real `~/.azlin` (#1079).
//! None needs Azure or the network: every assertion is about which file azlin
//! read, which it decides before it makes an Azure call.

use tempfile::TempDir;

use super::common::run_isolated;

/// Write a config file inside `dir` and return its path.
fn write_config(dir: &TempDir, name: &str, body: &str) -> std::path::PathBuf {
    let path = dir.path().join(name);
    std::fs::write(&path, body).unwrap();
    path
}

fn stdout_of(out: &std::process::Output) -> String {
    String::from_utf8_lossy(&out.stdout).to_string()
}

fn stderr_of(out: &std::process::Output) -> String {
    String::from_utf8_lossy(&out.stderr).to_string()
}

/// A command other than `new` must read the file `--config` names.
///
/// The default config in `AZLIN_CONFIG_DIR` names a different resource group,
/// so reading the wrong file is visible in the output rather than merely
/// unproven. This is the assertion that failed before the fix: `config get`
/// printed `rg-from-default-config` no matter what `--config` said.
#[test]
fn config_flag_is_read_by_a_command_other_than_new() {
    let dir = TempDir::new().unwrap();
    write_config(
        &dir,
        "config.toml",
        "default_resource_group = \"rg-from-default-config\"\n",
    );
    let explicit = write_config(
        &dir,
        "staging.toml",
        "default_resource_group = \"rg-from-explicit-config\"\n",
    );

    let out = run_isolated(
        &dir,
        &[
            "config",
            "get",
            "default_resource_group",
            "--config",
            explicit.to_str().unwrap(),
        ],
    );
    assert!(
        out.status.success(),
        "config get --config failed: {}",
        stderr_of(&out)
    );
    assert!(
        stdout_of(&out).contains("rg-from-explicit-config"),
        "--config was ignored; got: {}",
        stdout_of(&out)
    );
    assert!(
        !stdout_of(&out).contains("rg-from-default-config"),
        "--config fell back to the default config: {}",
        stdout_of(&out)
    );
}

/// Without `--config`, `AZLIN_CONFIG_DIR` still decides.
///
/// The override must not become the *only* way to select a config file: test
/// isolation (`tests/common.rs::run_isolated`) and every existing user's setup
/// depend on `AZLIN_CONFIG_DIR` and `~/.azlin` continuing to work.
#[test]
fn without_the_flag_the_config_dir_still_wins() {
    let dir = TempDir::new().unwrap();
    write_config(
        &dir,
        "config.toml",
        "default_resource_group = \"rg-from-default-config\"\n",
    );
    let out = run_isolated(&dir, &["config", "get", "default_resource_group"]);
    assert!(
        out.status.success(),
        "config get failed: {}",
        stderr_of(&out)
    );
    assert!(
        stdout_of(&out).contains("rg-from-default-config"),
        "AZLIN_CONFIG_DIR was not honoured: {}",
        stdout_of(&out)
    );
}

/// The destructive command from the issue must reach the file it was given.
///
/// `killall` resolves its resource group from config before it calls Azure, so
/// this asserts on that resolution and never reaches a mutating Azure call. The
/// resource group named here does not exist, and the only Azure command on the
/// path before the assertion is a read-only `az vm list`.
#[test]
fn config_flag_reaches_killall_resource_group_resolution() {
    let dir = TempDir::new().unwrap();

    // No config anywhere: killall cannot resolve a resource group.
    let without = run_isolated(&dir, &["killall", "--force"]);
    assert!(
        stderr_of(&without).contains("No resource group configured"),
        "expected killall with no config to fail on resource-group resolution, got: {}",
        stderr_of(&without)
    );

    // The same invocation with --config must get past that point, which it can
    // only do by having read the file.
    let explicit = write_config(
        &dir,
        "staging.toml",
        "default_resource_group = \"azlin-config-flag-regression-rg\"\n",
    );
    let with = run_isolated(
        &dir,
        &["killall", "--force", "--config", explicit.to_str().unwrap()],
    );
    assert!(
        !stderr_of(&with).contains("No resource group configured"),
        "killall --config still resolved no resource group, so the file was ignored: {}",
        stderr_of(&with)
    );
}

/// A `--config` path that does not exist must fail, not fall back.
///
/// Falling back to `~/.azlin/config.toml` for a typo'd path is the shape that
/// makes this bug destructive: the fallback names a different resource group,
/// so the command runs somewhere the user did not ask for.
#[test]
fn missing_config_file_fails_instead_of_falling_back() {
    let dir = TempDir::new().unwrap();
    write_config(
        &dir,
        "config.toml",
        "default_resource_group = \"rg-from-default-config\"\n",
    );
    let missing = dir.path().join("does-not-exist.toml");

    let out = run_isolated(
        &dir,
        &[
            "config",
            "get",
            "default_resource_group",
            "--config",
            missing.to_str().unwrap(),
        ],
    );
    assert!(
        !out.status.success(),
        "a missing --config file must not succeed; stdout: {}",
        stdout_of(&out)
    );
    assert_eq!(
        out.status.code(),
        Some(2),
        "expected exit 2 (the code load_user_config uses for an unusable config), stderr: {}",
        stderr_of(&out)
    );
    assert!(
        stderr_of(&out).contains("does-not-exist.toml"),
        "the error must name the file the user typed: {}",
        stderr_of(&out)
    );
    assert!(
        !stdout_of(&out).contains("rg-from-default-config"),
        "azlin fell back to the default config: {}",
        stdout_of(&out)
    );
}

/// A `--config` file that cannot be parsed must fail loudly too.
///
/// Same rule as #1080 applied to the explicit path: a config file that is
/// present but unreadable is an error, never "use defaults".
#[test]
fn unparseable_config_file_fails_loudly() {
    let dir = TempDir::new().unwrap();
    let bad = write_config(&dir, "broken.toml", "this is not = = valid toml\n");

    let out = run_isolated(
        &dir,
        &[
            "config",
            "get",
            "default_resource_group",
            "--config",
            bad.to_str().unwrap(),
        ],
    );
    assert_eq!(
        out.status.code(),
        Some(2),
        "expected exit 2 for an unparseable --config file, stderr: {}",
        stderr_of(&out)
    );
    assert!(
        stderr_of(&out).contains("broken.toml"),
        "the error must name the unparseable file: {}",
        stderr_of(&out)
    );
}

/// `--config` also decides where a config-mutating command writes.
///
/// Reading one file and writing another would be its own silent-degradation
/// bug: `azlin config set --config ./staging.toml` would report success and
/// leave staging.toml untouched.
#[test]
fn config_set_writes_to_the_file_the_flag_names() {
    let dir = TempDir::new().unwrap();
    write_config(
        &dir,
        "config.toml",
        "default_resource_group = \"rg-from-default-config\"\n",
    );
    let explicit = write_config(
        &dir,
        "staging.toml",
        "default_resource_group = \"rg-from-explicit-config\"\n",
    );

    let out = run_isolated(
        &dir,
        &[
            "config",
            "set",
            "default_resource_group",
            "rg-written-by-flag",
            "--config",
            explicit.to_str().unwrap(),
        ],
    );
    assert!(
        out.status.success(),
        "config set --config failed: {}",
        stderr_of(&out)
    );

    let written = std::fs::read_to_string(&explicit).unwrap();
    assert!(
        written.contains("rg-written-by-flag"),
        "the file named by --config was not updated: {written}"
    );
    let default_file = std::fs::read_to_string(dir.path().join("config.toml")).unwrap();
    assert!(
        default_file.contains("rg-from-default-config"),
        "the default config must not be touched when --config is given: {default_file}"
    );
}

/// `--config` must still be accepted after the subcommand, on every command.
///
/// The flag moved from 60 per-variant declarations to one global, so this is
/// what the move has to keep: `azlin <anything> --config <path>` still parses,
/// including on nested subcommands like `batch stop` and `env list` that never
/// declared it on their own variant.
///
/// `--help` trails each invocation so clap exits at parse time: this test is
/// about the argument surface, and nothing here should reach Azure.
#[test]
fn config_flag_is_still_accepted_on_subcommands() {
    let dir = TempDir::new().unwrap();
    let cfg = write_config(&dir, "staging.toml", "default_region = \"westus2\"\n");
    for command in [
        vec!["list"],
        vec!["killall"],
        vec!["batch", "stop"],
        vec!["env", "list"],
        vec!["context", "list"],
        vec!["new"],
        vec!["config", "show"],
    ] {
        let mut full = command.clone();
        full.push("--config");
        full.push(cfg.to_str().unwrap());
        full.push("--help");
        let out = run_isolated(&dir, &full);
        assert!(
            out.status.success(),
            "azlin {} --config <path> --help was rejected: {}",
            command.join(" "),
            stderr_of(&out)
        );
        assert!(
            stdout_of(&out).contains("--config"),
            "azlin {} --help does not advertise --config",
            command.join(" ")
        );
    }
}
