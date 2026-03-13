//! Scoped bastion tunnel for one-shot SSH/SCP operations through Azure Bastion.
//!
//! Starts an `az network bastion tunnel` subprocess bound to a local port,
//! then tears it down automatically on drop.

use anyhow::Result;
use std::sync::atomic::{AtomicU16, Ordering};

/// Global port counter to avoid collisions across concurrent tunnels.
static NEXT_PORT: AtomicU16 = AtomicU16::new(50200);

/// A running bastion tunnel that forwards a local port to a VM's SSH port.
/// The tunnel subprocess is killed when this struct is dropped.
pub struct ScopedBastionTunnel {
    pub local_port: u16,
    child: std::process::Child,
}

impl ScopedBastionTunnel {
    /// Spin up a bastion tunnel and wait briefly for it to establish.
    pub fn new(bastion_name: &str, resource_group: &str, vm_resource_id: &str) -> Result<Self> {
        let port = NEXT_PORT.fetch_add(1, Ordering::SeqCst);
        let child = std::process::Command::new("az")
            .args([
                "network",
                "bastion",
                "tunnel",
                "--name",
                bastion_name,
                "--resource-group",
                resource_group,
                "--target-resource-id",
                vm_resource_id,
                "--resource-port",
                "22",
                "--port",
                &port.to_string(),
            ])
            .stdout(std::process::Stdio::null())
            .stderr(std::process::Stdio::null())
            .spawn()?;
        // Wait briefly for tunnel to establish
        std::thread::sleep(std::time::Duration::from_secs(2));
        Ok(Self {
            local_port: port,
            child,
        })
    }
}

impl Drop for ScopedBastionTunnel {
    fn drop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

/// Build SSH args that route through a bastion tunnel (127.0.0.1 on a local port).
pub fn bastion_ssh_args(user: &str, local_port: u16, cmd: &str, connect_timeout: u64) -> Vec<String> {
    vec![
        "-o".to_string(),
        "StrictHostKeyChecking=accept-new".to_string(),
        "-o".to_string(),
        format!("ConnectTimeout={}", connect_timeout),
        "-o".to_string(),
        "BatchMode=yes".to_string(),
        "-p".to_string(),
        local_port.to_string(),
        format!("{}@127.0.0.1", user),
        cmd.to_string(),
    ]
}

/// Build SCP args that route through a bastion tunnel.
/// `sources` are local file paths, `remote_path` is the destination on the VM.
pub fn bastion_scp_args(
    user: &str,
    local_port: u16,
    sources: &[&str],
    remote_path: &str,
    connect_timeout: u64,
    recursive: bool,
) -> Vec<String> {
    let mut args = Vec::new();
    if recursive {
        args.push("-r".to_string());
    }
    args.extend_from_slice(&[
        "-o".to_string(),
        "StrictHostKeyChecking=accept-new".to_string(),
        "-o".to_string(),
        format!("ConnectTimeout={}", connect_timeout),
        "-o".to_string(),
        "BatchMode=yes".to_string(),
        "-P".to_string(),
        local_port.to_string(),
    ]);
    for src in sources {
        args.push(src.to_string());
    }
    args.push(format!("{}@127.0.0.1:{}", user, remote_path));
    args
}

/// Build SCP args for downloading from VM through bastion tunnel.
pub fn bastion_scp_download_args(
    user: &str,
    local_port: u16,
    remote_path: &str,
    local_dest: &str,
    connect_timeout: u64,
) -> Vec<String> {
    vec![
        "-o".to_string(),
        "StrictHostKeyChecking=accept-new".to_string(),
        "-o".to_string(),
        format!("ConnectTimeout={}", connect_timeout),
        "-o".to_string(),
        "BatchMode=yes".to_string(),
        "-P".to_string(),
        local_port.to_string(),
        format!("{}@127.0.0.1:{}", user, remote_path),
        local_dest.to_string(),
    ]
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_bastion_ssh_args_format() {
        let args = bastion_ssh_args("admin", 50200, "uptime", 30);
        assert!(args.contains(&"-p".to_string()));
        assert!(args.contains(&"50200".to_string()));
        assert!(args.contains(&"admin@127.0.0.1".to_string()));
        assert!(args.contains(&"ConnectTimeout=30".to_string()));
        assert_eq!(args.last().unwrap(), "uptime");
    }

    #[test]
    fn test_bastion_scp_args_format() {
        let args = bastion_scp_args("admin", 50201, &["/tmp/file.txt"], "~/", 30, false);
        assert!(args.contains(&"-P".to_string()));
        assert!(args.contains(&"50201".to_string()));
        assert!(args.contains(&"/tmp/file.txt".to_string()));
        assert!(args.contains(&"admin@127.0.0.1:~/".to_string()));
        assert!(!args.contains(&"-r".to_string()));
    }

    #[test]
    fn test_bastion_scp_args_recursive() {
        let args = bastion_scp_args("user", 50202, &["/tmp/dir"], "~/dest/", 10, true);
        assert_eq!(args[0], "-r");
    }

    #[test]
    fn test_bastion_scp_download_args() {
        let args = bastion_scp_download_args("admin", 50203, "~/file.txt", "/tmp/file.txt", 30);
        assert!(args.contains(&"admin@127.0.0.1:~/file.txt".to_string()));
        assert!(args.contains(&"/tmp/file.txt".to_string()));
    }
}
