#![cfg(unix)]

use azlin_azure::{AzureAuth, VmManager};
use std::os::unix::fs::PermissionsExt;
use std::path::PathBuf;
use std::sync::{Mutex, MutexGuard};

static ENV_LOCK: Mutex<()> = Mutex::new(());

struct AzureCliStub {
    _lock: MutexGuard<'static, ()>,
    _dir: tempfile::TempDir,
    log: PathBuf,
    old_path: Option<std::ffi::OsString>,
    old_log: Option<std::ffi::OsString>,
    old_fail: Option<std::ffi::OsString>,
}

impl AzureCliStub {
    fn new(fail: bool) -> Self {
        let lock = ENV_LOCK.lock().unwrap();
        let dir = tempfile::TempDir::new().unwrap();
        let az = dir.path().join("az");
        let log = dir.path().join("az-args.log");
        std::fs::write(
            &az,
            "#!/bin/sh\nprintf '%s\\n' \"$*\" > \"$AZLIN_TEST_AZ_LOG\"\n\
             if [ \"$AZLIN_TEST_AZ_FAIL\" = 1 ]; then\n\
               echo 'OperationNotAllowed: synthetic wrapper failure' >&2\n\
               exit 1\n\
             fi\n\
             echo '{}'\n",
        )
        .unwrap();
        std::fs::set_permissions(&az, std::fs::Permissions::from_mode(0o755)).unwrap();

        let old_path = std::env::var_os("PATH");
        let old_log = std::env::var_os("AZLIN_TEST_AZ_LOG");
        let old_fail = std::env::var_os("AZLIN_TEST_AZ_FAIL");
        let inherited = old_path.clone().unwrap_or_default();
        let mut paths = vec![dir.path().to_path_buf()];
        paths.extend(std::env::split_paths(&inherited));
        std::env::set_var("PATH", std::env::join_paths(paths).unwrap());
        std::env::set_var("AZLIN_TEST_AZ_LOG", &log);
        std::env::set_var("AZLIN_TEST_AZ_FAIL", if fail { "1" } else { "0" });

        Self {
            _lock: lock,
            _dir: dir,
            log,
            old_path,
            old_log,
            old_fail,
        }
    }

    fn args(&self) -> String {
        std::fs::read_to_string(&self.log).unwrap()
    }
}

impl Drop for AzureCliStub {
    fn drop(&mut self) {
        restore_env("PATH", self.old_path.take());
        restore_env("AZLIN_TEST_AZ_LOG", self.old_log.take());
        restore_env("AZLIN_TEST_AZ_FAIL", self.old_fail.take());
    }
}

fn restore_env(name: &str, value: Option<std::ffi::OsString>) {
    match value {
        Some(value) => std::env::set_var(name, value),
        None => std::env::remove_var(name),
    }
}

fn manager() -> VmManager {
    let auth = AzureAuth::new_with_subscription("00000000-0000-0000-0000-000000000001").unwrap();
    VmManager::with_timeout(&auth, 5)
}

#[test]
fn delete_resource_group_constructs_expected_azure_cli_operation() {
    let stub = AzureCliStub::new(false);

    manager()
        .delete_resource_group("synthetic-azure-rg")
        .unwrap();

    assert_eq!(
        stub.args().trim(),
        "group delete --name synthetic-azure-rg --yes --output json"
    );
}

#[test]
fn delete_resource_group_propagates_azure_cli_wrapper_failure() {
    let stub = AzureCliStub::new(true);

    let error = manager()
        .delete_resource_group("synthetic-failing-rg")
        .unwrap_err();
    let chain = format!("{error:#}");

    assert!(chain.contains("synthetic-failing-rg"));
    assert!(chain.contains("OperationNotAllowed"));
    assert_eq!(
        stub.args().trim(),
        "group delete --name synthetic-failing-rg --yes --output json"
    );
}
