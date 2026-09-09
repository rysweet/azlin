#![cfg(unix)]

use std::os::unix::fs::PermissionsExt;
use std::path::{Path, PathBuf};
use std::process::Command;

const RG: &str = "synthetic-destroy-rg";
const VM: &str = "synthetic-destroy-vm";

struct Sandbox {
    dir: tempfile::TempDir,
    log: PathBuf,
}

impl Sandbox {
    fn new() -> Self {
        let dir = tempfile::TempDir::new().unwrap();
        let root = dir.path();
        std::fs::create_dir(root.join("bin")).unwrap();
        std::fs::create_dir(root.join("home")).unwrap();
        std::fs::create_dir(root.join("config")).unwrap();
        let log = root.join("az-args.log");
        let az = root.join("bin/az");
        std::fs::write(
            &az,
            "#!/bin/sh\nprintf '%s\\n' \"$*\" >> \"$AZLIN_TEST_AZ_LOG\"\n\
             case \"$*\" in\n\
               *'account show'*) echo '{\"id\":\"00000000-0000-0000-0000-000000000001\",\
                 \"tenantId\":\"00000000-0000-0000-0000-000000000002\",\
                 \"name\":\"synthetic\",\"user\":{\"name\":\"test@example.com\"}}' ;;\n\
               *'group delete'*|*'vm delete'*)\n\
                 if [ \"$AZLIN_TEST_DELETE_FAIL\" = 1 ]; then\n\
                   echo 'OperationNotAllowed: synthetic delete failure' >&2\n\
                   exit 1\n\
                 fi\n\
                 echo '{}' ;;\n\
               *) echo '[]' ;;\n\
             esac\n",
        )
        .unwrap();
        std::fs::set_permissions(&az, std::fs::Permissions::from_mode(0o755)).unwrap();
        Self { dir, log }
    }

    fn run(&self, args: &[&str], fail_delete: bool) -> (String, String, i32) {
        let inherited = std::env::var("PATH").unwrap_or_default();
        let output = Command::new(env!("CARGO_BIN_EXE_azlin"))
            .args(args)
            .env(
                "PATH",
                format!("{}:{inherited}", self.dir.path().join("bin").display()),
            )
            .env("HOME", self.dir.path().join("home"))
            .env("AZLIN_CONFIG_DIR", self.dir.path().join("config"))
            .env("AZLIN_TEST_AZ_LOG", &self.log)
            .env(
                "AZLIN_TEST_DELETE_FAIL",
                if fail_delete { "1" } else { "0" },
            )
            .env_remove("AZURE_SUBSCRIPTION_ID")
            .env_remove("AZURE_TENANT_ID")
            .output()
            .unwrap();
        (
            String::from_utf8_lossy(&output.stdout).to_string(),
            String::from_utf8_lossy(&output.stderr).to_string(),
            output.status.code().unwrap_or(-1),
        )
    }

    fn calls(&self) -> String {
        std::fs::read_to_string(&self.log).unwrap_or_default()
    }
}

fn combined(stdout: &str, stderr: &str) -> String {
    format!("{stdout}{stderr}")
}

fn assert_no_azure_calls(log: &Path) {
    assert!(
        !log.exists() || std::fs::read_to_string(log).unwrap().is_empty(),
        "dry-run unexpectedly invoked Azure: {}",
        std::fs::read_to_string(log).unwrap_or_default()
    );
}

#[test]
fn vm_dry_run_succeeds_before_auth_and_describes_vm_only_scope() {
    let sandbox = Sandbox::new();

    let (stdout, stderr, code) =
        sandbox.run(&["destroy", VM, "--resource-group", RG, "--dry-run"], false);
    let output = combined(&stdout, &stderr).to_lowercase();

    assert_eq!(code, 0, "{output}");
    assert!(output.contains("dry run"));
    assert!(output.contains(VM));
    assert!(output.contains(RG));
    assert!(output.contains("owned session resources"));
    assert!(output.contains("resource group and unrelated resources would remain"));
    assert!(!output.contains("all resources"));
    assert_no_azure_calls(&sandbox.log);
}

#[test]
fn resource_group_dry_run_succeeds_before_auth_and_describes_full_scope() {
    let sandbox = Sandbox::new();

    let (stdout, stderr, code) = sandbox.run(
        &[
            "destroy",
            VM,
            "--resource-group",
            RG,
            "--delete-rg",
            "--dry-run",
        ],
        false,
    );
    let output = combined(&stdout, &stderr).to_lowercase();

    assert_eq!(code, 0, "{output}");
    assert!(output.contains("dry run"));
    assert!(output.contains("resource group"));
    assert!(output.contains(RG));
    assert!(output.contains("all resources"));
    assert_no_azure_calls(&sandbox.log);
}

#[test]
fn unconfirmed_resource_group_destroy_never_reaches_azure() {
    let sandbox = Sandbox::new();

    let (stdout, stderr, code) = sandbox.run(
        &["destroy", VM, "--resource-group", RG, "--delete-rg"],
        false,
    );
    let output = combined(&stdout, &stderr).to_lowercase();

    assert_ne!(code, 0);
    assert!(output.contains("confirmation required"));
    assert!(output.contains("--force"));
    assert_no_azure_calls(&sandbox.log);
}

#[test]
fn forced_resource_group_destroy_invokes_only_group_delete() {
    let sandbox = Sandbox::new();

    let (stdout, stderr, code) = sandbox.run(
        &[
            "destroy",
            VM,
            "--resource-group",
            RG,
            "--delete-rg",
            "--force",
        ],
        false,
    );
    let output = combined(&stdout, &stderr).to_lowercase();
    let calls = sandbox.calls();

    assert_eq!(code, 0, "{output}");
    assert!(calls.contains(&format!("group delete --name {RG} --yes")));
    assert!(!calls.contains("vm delete"));
    assert!(output.contains("deleted resource group"));
    assert!(output.contains(RG));
}

#[test]
fn forced_vm_destroy_invokes_only_vm_delete() {
    let sandbox = Sandbox::new();

    let (stdout, stderr, code) =
        sandbox.run(&["destroy", VM, "--resource-group", RG, "--force"], false);
    let output = combined(&stdout, &stderr).to_lowercase();
    let calls = sandbox.calls();

    assert_eq!(code, 0, "{output}");
    assert!(calls.contains(&format!(
        "vm delete --resource-group {RG} --name {VM} --yes"
    )));
    assert!(!calls.contains("group delete"));
    assert!(output.contains("destroyed"));
    assert!(output.contains(VM));
}

#[test]
fn group_delete_failure_is_contextual_and_has_no_success_output() {
    let sandbox = Sandbox::new();

    let (stdout, stderr, code) = sandbox.run(
        &[
            "destroy",
            VM,
            "--resource-group",
            RG,
            "--delete-rg",
            "--force",
        ],
        true,
    );
    let output = combined(&stdout, &stderr).to_lowercase();

    assert_ne!(code, 0, "{output}");
    assert!(output.contains("failed to delete resource group"));
    assert!(output.contains(RG));
    assert!(output.contains("operationnotallowed"));
    assert!(!output.contains("deleted resource group"));
}

#[test]
fn vm_delete_failure_is_contextual_and_has_no_success_output() {
    let sandbox = Sandbox::new();

    let (stdout, stderr, code) =
        sandbox.run(&["destroy", VM, "--resource-group", RG, "--force"], true);
    let output = combined(&stdout, &stderr).to_lowercase();

    assert_ne!(code, 0, "{output}");
    assert!(output.contains("failed to delete vm"));
    assert!(output.contains(VM));
    assert!(output.contains(RG));
    assert!(output.contains("operationnotallowed"));
    assert!(!output.contains("destroyed"));
}
