use std::process::Command;

/// Build a Command targeting the azlin binary from this workspace.
///
/// Pointed at an empty config directory, not the developer's. These tests
/// assert what azlin does with no Azure configured; on a workstation with a
/// real `~/.azlin` they would instead read that config, find a resource group
/// and make live Azure calls — passing here, failing in CI, and touching the
/// developer's own subscription on the way (#1079).
///
/// The directory is created once per test process and is only ever **read**:
/// a test that writes config gives itself a `HOME` or an `AZLIN_CONFIG_DIR` of
/// its own, and [`run_azlin_with_env`] stands this default down when it sees
/// one. Sharing a directory a test writes to would make those tests race each
/// other, which is the opposite of what this isolation is for.
pub fn azlin_cmd() -> Command {
    static CONFIG_DIR: std::sync::OnceLock<tempfile::TempDir> = std::sync::OnceLock::new();
    let dir = CONFIG_DIR.get_or_init(|| tempfile::TempDir::new().expect("temp config dir"));
    let mut cmd = Command::new(env!("CARGO_BIN_EXE_azlin"));
    cmd.env("AZLIN_CONFIG_DIR", dir.path());
    cmd
}

/// Run azlin with the given arguments and return (stdout, stderr, exit_code).
pub fn run_azlin(args: &[&str]) -> (String, String, i32) {
    let output = azlin_cmd()
        .args(args)
        .env_remove("AZURE_SUBSCRIPTION_ID")
        .env_remove("AZURE_TENANT_ID")
        .output()
        .expect("Failed to run azlin binary");
    (
        String::from_utf8_lossy(&output.stdout).to_string(),
        String::from_utf8_lossy(&output.stderr).to_string(),
        output.status.code().unwrap_or(-1),
    )
}

/// Run azlin with extra environment variables.
#[allow(dead_code)]
pub fn run_azlin_with_env(args: &[&str], env_vars: &[(&str, &str)]) -> (String, String, i32) {
    let mut cmd = azlin_cmd();
    cmd.args(args)
        .env_remove("AZURE_SUBSCRIPTION_ID")
        .env_remove("AZURE_TENANT_ID");
    // A caller supplying its own `HOME` or `AZLIN_CONFIG_DIR` is isolating
    // itself, usually because it writes config. The shared read-only default
    // would override that and put every such test in one directory, racing.
    if env_vars
        .iter()
        .any(|(k, _)| *k == "HOME" || *k == "AZLIN_CONFIG_DIR")
    {
        cmd.env_remove("AZLIN_CONFIG_DIR");
    }
    for (k, v) in env_vars {
        cmd.env(k, v);
    }
    let output = cmd.output().expect("Failed to run azlin binary");
    (
        String::from_utf8_lossy(&output.stdout).to_string(),
        String::from_utf8_lossy(&output.stderr).to_string(),
        output.status.code().unwrap_or(-1),
    )
}
