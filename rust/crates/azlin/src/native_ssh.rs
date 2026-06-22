//! Native SSH execution via `azlin-ssh` (russh).
//!
//! Provides a global connection pool that `VmSshTarget` uses for direct SSH
//! to VMs with public IPs. Falls back to subprocess SSH on any error.

use anyhow::Result;
use azlin_ssh::{SshConfig, SshPool};
use std::path::PathBuf;
use std::sync::OnceLock;
use std::time::Duration;
use tracing::{debug, warn};

/// Global SSH connection pool, lazily initialized.
static POOL: OnceLock<SshPool> = OnceLock::new();

/// Get or initialize the global SSH connection pool.
fn global_pool() -> &'static SshPool {
    POOL.get_or_init(|| SshPool::new(20, Duration::from_secs(300)))
}

/// Resolve the preferred SSH private key path.
fn resolve_key_path() -> Option<PathBuf> {
    let ssh_dir = dirs::home_dir()?.join(".ssh");
    crate::key_helpers::find_preferred_private_key(&ssh_dir)
}

/// Execute a command on a remote host using native russh.
///
/// Returns `Ok((exit_code, stdout, stderr))` on success, or `Err` if the
/// connection itself fails (caller should fall back to subprocess SSH).
pub async fn native_exec(ip: &str, user: &str, cmd: &str) -> Result<(i32, String, String)> {
    let key_path = resolve_key_path()
        .ok_or_else(|| anyhow::anyhow!("no SSH private key found for native SSH"))?;

    let config = SshConfig::new(ip, user, key_path);
    let pool = global_pool();

    let mut client = pool
        .get_or_connect(&config)
        .await
        .map_err(|e| anyhow::anyhow!("native SSH connect to {}: {}", ip, e))?;

    let result = client.execute(cmd).await;

    match result {
        Ok(r) => {
            pool.release(client).await;
            debug!("native SSH exec on {} completed (exit={})", ip, r.exit_code);
            Ok((r.exit_code, r.stdout, r.stderr))
        }
        Err(e) => {
            warn!("native SSH exec failed on {}: {}", ip, e);
            Err(anyhow::anyhow!("native SSH exec: {}", e))
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn resolve_key_path_returns_option() {
        let _ = resolve_key_path();
    }

    #[test]
    fn global_pool_is_consistent() {
        let p1 = global_pool() as *const SshPool;
        let p2 = global_pool() as *const SshPool;
        assert_eq!(p1, p2, "global pool should be a singleton");
    }
}
