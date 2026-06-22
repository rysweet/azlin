use std::process::Command;

/// Build a Command targeting the azlin binary from this workspace.
pub fn azlin_cmd() -> Command {
    Command::new(env!("CARGO_BIN_EXE_azlin"))
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
