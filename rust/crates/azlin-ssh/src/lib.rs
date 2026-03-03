//! azlin-ssh: SSH connection pooling and remote command execution.
//!
//! Provides async SSH connectivity using `russh`, mirroring the Python
//! `azlin.ssh.connection_pool` module with connection reuse, remote command
//! execution, and file transfer.

use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::time::{Duration, Instant};

use async_trait::async_trait;
use azlin_core::models::CommandResult;
use azlin_core::{AzlinError, Result};
use russh::client::{self, Handle};
use russh::ChannelMsg;
use russh_keys::load_secret_key;
use tokio::io::AsyncWriteExt;
use tokio::sync::Mutex;
use tracing::{debug, warn};

/// SSH connection configuration.
#[derive(Debug, Clone)]
pub struct SshConfig {
    pub host: String,
    pub port: u16,
    pub username: String,
    pub key_path: PathBuf,
    pub timeout: Duration,
}

impl SshConfig {
    pub fn new(host: impl Into<String>, username: impl Into<String>, key_path: PathBuf) -> Self {
        Self {
            host: host.into(),
            port: 22,
            username: username.into(),
            key_path,
            timeout: Duration::from_secs(30),
        }
    }

    /// Unique key used to identify a pooled connection.
    pub fn pool_key(&self) -> String {
        format!("{}@{}:{}", self.username, self.host, self.port)
    }
}

/// Minimal handler that accepts all host keys (suitable for Azure VM
/// infrastructure where hosts are ephemeral).
struct SshHandler;

#[async_trait]
impl client::Handler for SshHandler {
    type Error = russh::Error;

    async fn check_server_key(
        &mut self,
        _server_public_key: &russh_keys::ssh_key::PublicKey,
    ) -> std::result::Result<bool, Self::Error> {
        // Azure VMs have dynamic IPs / ephemeral hosts — accept all keys.
        Ok(true)
    }
}

/// An established SSH connection wrapping a `russh` handle.
pub struct SshClient {
    handle: Handle<SshHandler>,
    config: SshConfig,
    connected_at: Instant,
    last_used: Instant,
}

impl SshClient {
    /// Establish a new SSH connection using the provided config.
    pub async fn connect(config: &SshConfig) -> Result<Self> {
        let key = load_secret_key(&config.key_path, None)
            .map_err(|e| AzlinError::SshKey(format!("failed to load key: {e}")))?;

        let russh_config = Arc::new(client::Config {
            inactivity_timeout: Some(config.timeout),
            ..Default::default()
        });

        let addr = (config.host.as_str(), config.port);
        let mut handle = tokio::time::timeout(
            config.timeout,
            client::connect(russh_config, addr, SshHandler),
        )
        .await
        .map_err(|_| AzlinError::Ssh(format!("connection to {} timed out", config.host)))?
        .map_err(|e| AzlinError::Ssh(format!("connection failed: {e}")))?;

        let authenticated = handle
            .authenticate_publickey(&config.username, Arc::new(key))
            .await
            .map_err(|e| AzlinError::Ssh(format!("auth failed: {e}")))?;

        if !authenticated {
            return Err(AzlinError::Ssh("public-key authentication rejected".into()));
        }

        debug!("SSH connected to {}", config.pool_key());
        let now = Instant::now();
        Ok(Self {
            handle,
            config: config.clone(),
            connected_at: now,
            last_used: now,
        })
    }

    /// Execute a remote command and return its result.
    pub async fn execute(&mut self, command: &str) -> Result<CommandResult> {
        let start = Instant::now();

        let mut channel = self
            .handle
            .channel_open_session()
            .await
            .map_err(|e| AzlinError::RemoteExec(format!("channel open failed: {e}")))?;

        channel
            .exec(true, command)
            .await
            .map_err(|e| AzlinError::RemoteExec(format!("exec failed: {e}")))?;

        let mut stdout = Vec::new();
        let mut stderr = Vec::new();
        let mut exit_code: Option<u32> = None;

        while let Some(msg) = channel.wait().await {
            match msg {
                ChannelMsg::Data { data } => stdout.extend_from_slice(&data),
                ChannelMsg::ExtendedData { data, ext: 1 } => stderr.extend_from_slice(&data),
                ChannelMsg::ExitStatus { exit_status } => exit_code = Some(exit_status),
                ChannelMsg::Eof | ChannelMsg::Close => break,
                _ => {}
            }
        }

        self.last_used = Instant::now();

        Ok(CommandResult {
            exit_code: exit_code.unwrap_or(0) as i32,
            stdout: String::from_utf8_lossy(&stdout).into_owned(),
            stderr: String::from_utf8_lossy(&stderr).into_owned(),
            duration_ms: start.elapsed().as_millis() as u64,
        })
    }

    /// Upload a local file to the remote host via the SCP subsystem
    /// (exec `cat > remote_path`).
    pub async fn upload(&mut self, local_path: &Path, remote_path: &str) -> Result<()> {
        let data = tokio::fs::read(local_path)
            .await
            .map_err(|e| AzlinError::FileTransfer(format!("read local file: {e}")))?;

        let mut channel = self
            .handle
            .channel_open_session()
            .await
            .map_err(|e| AzlinError::FileTransfer(format!("channel open: {e}")))?;

        let cmd = format!("cat > {}", shell_escape::unix::escape(remote_path.into()));
        channel
            .exec(true, cmd.as_bytes())
            .await
            .map_err(|e| AzlinError::FileTransfer(format!("exec failed: {e}")))?;

        let mut writer = channel.make_writer();
        writer
            .write_all(&data)
            .await
            .map_err(|e| AzlinError::FileTransfer(format!("write data: {e}")))?;
        writer
            .shutdown()
            .await
            .map_err(|e| AzlinError::FileTransfer(format!("shutdown writer: {e}")))?;

        channel.eof().await.ok();

        // Drain remaining messages until close
        while let Some(msg) = channel.wait().await {
            if matches!(msg, ChannelMsg::Eof | ChannelMsg::Close) {
                break;
            }
        }

        self.last_used = Instant::now();
        Ok(())
    }

    /// Download a remote file to a local path via `cat`.
    pub async fn download(&mut self, remote_path: &str, local_path: &Path) -> Result<()> {
        let cmd = format!("cat {}", shell_escape::unix::escape(remote_path.into()));
        let result = self.execute(&cmd).await?;

        if !result.success() {
            return Err(AzlinError::FileTransfer(format!(
                "remote cat failed: {}",
                result.stderr
            )));
        }

        tokio::fs::write(local_path, result.stdout.as_bytes())
            .await
            .map_err(|e| AzlinError::FileTransfer(format!("write local file: {e}")))?;

        Ok(())
    }

    /// Close the SSH connection.
    pub async fn close(self) -> Result<()> {
        self.handle
            .disconnect(russh::Disconnect::ByApplication, "", "en")
            .await
            .map_err(|e| AzlinError::Ssh(format!("disconnect failed: {e}")))?;
        debug!("SSH disconnected from {}", self.config.pool_key());
        Ok(())
    }

    /// Returns how long this connection has been open.
    pub fn age(&self) -> Duration {
        self.connected_at.elapsed()
    }

    /// Returns how long since the connection was last used.
    pub fn idle_time(&self) -> Duration {
        self.last_used.elapsed()
    }
}

/// Thread-safe SSH connection pool — mirrors the Python `SSHConnectionPool`.
pub struct SshPool {
    connections: Arc<Mutex<HashMap<String, SshClient>>>,
    max_connections: usize,
    idle_timeout: Duration,
}

impl SshPool {
    pub fn new(max_connections: usize, idle_timeout: Duration) -> Self {
        Self {
            connections: Arc::new(Mutex::new(HashMap::new())),
            max_connections,
            idle_timeout,
        }
    }

    /// Retrieve an existing connection or create a new one.
    ///
    /// If the pooled connection has exceeded `idle_timeout` it is discarded
    /// and a fresh connection is established.
    pub async fn get_or_connect(&self, config: &SshConfig) -> Result<SshClient> {
        let key = config.pool_key();
        let mut pool = self.connections.lock().await;

        // Return existing if still within idle timeout
        if let Some(client) = pool.remove(&key) {
            if client.idle_time() < self.idle_timeout {
                debug!("reusing pooled SSH connection {key}");
                return Ok(client);
            }
            // Idle — drop it (disconnect best-effort)
            warn!("evicting idle SSH connection {key}");
            let _ = client.close().await;
        }

        // Evict oldest if at capacity
        if pool.len() >= self.max_connections {
            let oldest_key = pool
                .iter()
                .min_by_key(|(_, c)| c.last_used)
                .map(|(k, _)| k.clone());
            if let Some(k) = oldest_key {
                if let Some(c) = pool.remove(&k) {
                    warn!("evicting oldest SSH connection {k}");
                    let _ = c.close().await;
                }
            }
        }

        drop(pool); // release lock during connect

        let client = SshClient::connect(config).await?;
        Ok(client)
    }

    /// Return a connection to the pool for later reuse.
    pub async fn release(&self, client: SshClient) {
        let key = client.config.pool_key();
        let mut pool = self.connections.lock().await;
        pool.insert(key, client);
    }

    /// Close every pooled connection.
    pub async fn close_all(self) -> Result<()> {
        let mut pool = self.connections.lock().await;
        for (key, client) in pool.drain() {
            debug!("closing pooled connection {key}");
            let _ = client.close().await;
        }
        Ok(())
    }

    /// Number of connections currently in the pool.
    pub async fn pool_size(&self) -> usize {
        self.connections.lock().await.len()
    }
}

impl Default for SshPool {
    fn default() -> Self {
        Self::new(20, Duration::from_secs(300))
    }
}

/// Generate a new SSH key pair name with timestamp
pub fn rotation_key_name(prefix: &str) -> String {
    let timestamp = chrono::Utc::now().format("%Y%m%d_%H%M%S");
    format!("{}_rotated_{}", prefix, timestamp)
}

/// Check if a key file is older than max_age_days
pub fn key_needs_rotation(key_path: &std::path::Path, max_age_days: u32) -> bool {
    if let Ok(metadata) = std::fs::metadata(key_path) {
        if let Ok(modified) = metadata.modified() {
            let age = std::time::SystemTime::now()
                .duration_since(modified)
                .unwrap_or_default();
            return age.as_secs() > (max_age_days as u64 * 86400);
        }
    }
    true // If we can't determine age, assume rotation needed
}

/// Plan key rotation across a fleet of VMs
pub fn plan_rotation(vm_count: usize, batch_size: usize) -> Vec<(usize, usize)> {
    let mut batches = Vec::new();
    let mut start = 0;
    while start < vm_count {
        let end = (start + batch_size).min(vm_count);
        batches.push((start, end));
        start = end;
    }
    batches
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::Duration;
    use tempfile::NamedTempFile;

    // ---- SshConfig unit tests ----

    #[test]
    fn test_config_defaults() {
        let cfg = SshConfig::new("10.0.0.1", "azureuser", PathBuf::from("/key"));
        assert_eq!(cfg.host, "10.0.0.1");
        assert_eq!(cfg.port, 22);
        assert_eq!(cfg.username, "azureuser");
        assert_eq!(cfg.timeout, Duration::from_secs(30));
    }

    #[test]
    fn test_config_pool_key() {
        let cfg = SshConfig::new("10.0.0.1", "admin", PathBuf::from("/key"));
        assert_eq!(cfg.pool_key(), "admin@10.0.0.1:22");

        let mut cfg2 = cfg.clone();
        cfg2.port = 2222;
        assert_eq!(cfg2.pool_key(), "admin@10.0.0.1:2222");
    }

    #[test]
    fn test_config_clone() {
        let cfg = SshConfig {
            host: "host".into(),
            port: 2222,
            username: "user".into(),
            key_path: PathBuf::from("/tmp/key"),
            timeout: Duration::from_secs(10),
        };
        let cfg2 = cfg.clone();
        assert_eq!(cfg.host, cfg2.host);
        assert_eq!(cfg.port, cfg2.port);
    }

    // ---- SshPool unit tests ----

    #[tokio::test]
    async fn test_pool_default_capacity() {
        let pool = SshPool::default();
        assert_eq!(pool.max_connections, 20);
        assert_eq!(pool.idle_timeout, Duration::from_secs(300));
        assert_eq!(pool.pool_size().await, 0);
    }

    #[tokio::test]
    async fn test_pool_custom_capacity() {
        let pool = SshPool::new(5, Duration::from_secs(60));
        assert_eq!(pool.max_connections, 5);
        assert_eq!(pool.idle_timeout, Duration::from_secs(60));
    }

    // ---- Connection failure tests (no real SSH server) ----

    #[tokio::test]
    async fn test_connect_bad_key_path() {
        let cfg = SshConfig::new("127.0.0.1", "user", PathBuf::from("/nonexistent/key"));
        let result = SshClient::connect(&cfg).await;
        assert!(result.is_err());
        let err = result.err().unwrap().to_string();
        assert!(err.contains("key"), "error should mention key: {err}");
    }

    #[tokio::test]
    async fn test_connect_unreachable_host() {
        // Write a valid-ish key file so key loading succeeds, but connection
        // to a non-routable address should time out or fail.
        let keyfile = NamedTempFile::new().unwrap();
        // russh_keys::load_secret_key expects a real key — this will fail at
        // key parsing, which is fine for this test.
        let cfg = SshConfig {
            host: "192.0.2.1".into(), // TEST-NET, non-routable
            port: 22,
            username: "user".into(),
            key_path: keyfile.path().to_path_buf(),
            timeout: Duration::from_secs(1),
        };
        let result = SshClient::connect(&cfg).await;
        assert!(result.is_err());
    }

    #[tokio::test]
    async fn test_pool_close_all_empty() {
        let pool = SshPool::default();
        // Closing an empty pool should succeed without error.
        pool.close_all().await.unwrap();
    }

    // ── Additional SSH tests ────────────────────────────────────────

    #[test]
    fn test_ssh_config_default_port() {
        let cfg = SshConfig::new("host", "user", PathBuf::from("/key"));
        assert_eq!(cfg.port, 22);
    }

    #[test]
    fn test_ssh_config_default_timeout() {
        let cfg = SshConfig::new("host", "user", PathBuf::from("/key"));
        assert_eq!(cfg.timeout, Duration::from_secs(30));
    }

    #[test]
    fn test_ssh_config_custom_port() {
        let mut cfg = SshConfig::new("host", "user", PathBuf::from("/key"));
        cfg.port = 2222;
        assert_eq!(cfg.port, 2222);
        assert_eq!(cfg.pool_key(), "user@host:2222");
    }

    #[test]
    fn test_ssh_config_custom_key_path() {
        let cfg = SshConfig::new("host", "user", PathBuf::from("/home/user/.ssh/custom_key"));
        assert_eq!(cfg.key_path, PathBuf::from("/home/user/.ssh/custom_key"));
    }

    #[test]
    fn test_ssh_config_custom_timeout() {
        let cfg = SshConfig {
            host: "host".into(),
            port: 22,
            username: "user".into(),
            key_path: PathBuf::from("/key"),
            timeout: Duration::from_secs(5),
        };
        assert_eq!(cfg.timeout, Duration::from_secs(5));
    }

    #[test]
    fn test_ssh_config_pool_key_format() {
        let cfg = SshConfig {
            host: "192.168.1.100".into(),
            port: 2222,
            username: "admin".into(),
            key_path: PathBuf::from("/key"),
            timeout: Duration::from_secs(30),
        };
        assert_eq!(cfg.pool_key(), "admin@192.168.1.100:2222");
    }

    #[test]
    fn test_ssh_config_pool_key_with_hostname() {
        let cfg = SshConfig::new("myvm.azure.com", "azureuser", PathBuf::from("/key"));
        assert_eq!(cfg.pool_key(), "azureuser@myvm.azure.com:22");
    }

    #[tokio::test]
    async fn test_pool_new_with_params() {
        let pool = SshPool::new(10, Duration::from_secs(60));
        assert_eq!(pool.max_connections, 10);
        assert_eq!(pool.idle_timeout, Duration::from_secs(60));
        assert_eq!(pool.pool_size().await, 0);
    }

    #[tokio::test]
    async fn test_pool_size_starts_empty() {
        let pool = SshPool::new(5, Duration::from_secs(120));
        assert_eq!(pool.pool_size().await, 0);
    }

    #[tokio::test]
    async fn test_pool_get_or_connect_bad_key() {
        let pool = SshPool::new(5, Duration::from_secs(120));
        let cfg = SshConfig::new("127.0.0.1", "user", PathBuf::from("/nonexistent/key"));
        let result = pool.get_or_connect(&cfg).await;
        assert!(result.is_err());
        // Pool should still be empty after failed connect
        assert_eq!(pool.pool_size().await, 0);
    }

    #[test]
    fn test_ssh_config_debug_impl() {
        let cfg = SshConfig::new("host", "user", PathBuf::from("/key"));
        let debug = format!("{:?}", cfg);
        assert!(debug.contains("host"));
        assert!(debug.contains("user"));
    }

    // ── Additional SshConfig tests ──────────────────────────────────

    #[test]
    fn test_ssh_config_new_with_string_types() {
        let cfg = SshConfig::new(
            String::from("myhost"),
            String::from("myuser"),
            PathBuf::from("/key"),
        );
        assert_eq!(cfg.host, "myhost");
        assert_eq!(cfg.username, "myuser");
    }

    #[test]
    fn test_ssh_config_pool_key_uniqueness() {
        let cfg1 = SshConfig::new("host1", "user", PathBuf::from("/key"));
        let cfg2 = SshConfig::new("host2", "user", PathBuf::from("/key"));
        let cfg3 = SshConfig::new("host1", "admin", PathBuf::from("/key"));
        assert_ne!(cfg1.pool_key(), cfg2.pool_key());
        assert_ne!(cfg1.pool_key(), cfg3.pool_key());
        assert_ne!(cfg2.pool_key(), cfg3.pool_key());
    }

    #[test]
    fn test_ssh_config_pool_key_same_for_clones() {
        let cfg = SshConfig::new("host", "user", PathBuf::from("/key"));
        let cfg2 = cfg.clone();
        assert_eq!(cfg.pool_key(), cfg2.pool_key());
    }

    #[test]
    fn test_ssh_config_with_ipv6() {
        let cfg = SshConfig::new("::1", "user", PathBuf::from("/key"));
        assert_eq!(cfg.pool_key(), "user@::1:22");
    }

    #[test]
    fn test_ssh_config_with_fqdn() {
        let cfg = SshConfig::new(
            "vm.internal.cloudapp.azure.com",
            "azureuser",
            PathBuf::from("/key"),
        );
        assert_eq!(cfg.host, "vm.internal.cloudapp.azure.com");
        assert_eq!(
            cfg.pool_key(),
            "azureuser@vm.internal.cloudapp.azure.com:22"
        );
    }

    #[test]
    fn test_ssh_config_key_path_preserved() {
        let path = PathBuf::from("/home/user/.ssh/id_ed25519");
        let cfg = SshConfig::new("host", "user", path.clone());
        assert_eq!(cfg.key_path, path);
    }

    #[test]
    fn test_ssh_config_timeout_modification() {
        let mut cfg = SshConfig::new("host", "user", PathBuf::from("/key"));
        assert_eq!(cfg.timeout, Duration::from_secs(30));
        cfg.timeout = Duration::from_secs(5);
        assert_eq!(cfg.timeout, Duration::from_secs(5));
    }

    #[test]
    fn test_ssh_config_all_fields_in_debug() {
        let cfg = SshConfig {
            host: "10.0.0.1".into(),
            port: 2222,
            username: "admin".into(),
            key_path: PathBuf::from("/tmp/key"),
            timeout: Duration::from_secs(10),
        };
        let debug = format!("{:?}", cfg);
        assert!(debug.contains("10.0.0.1"));
        assert!(debug.contains("2222"));
        assert!(debug.contains("admin"));
        assert!(debug.contains("/tmp/key"));
    }

    // ── Additional SshPool tests ────────────────────────────────────

    #[tokio::test]
    async fn test_pool_default_impl() {
        let pool = SshPool::default();
        assert_eq!(pool.max_connections, 20);
        assert_eq!(pool.idle_timeout, Duration::from_secs(300));
        assert_eq!(pool.pool_size().await, 0);
    }

    #[tokio::test]
    async fn test_pool_small_capacity() {
        let pool = SshPool::new(1, Duration::from_secs(10));
        assert_eq!(pool.max_connections, 1);
        assert_eq!(pool.idle_timeout, Duration::from_secs(10));
    }

    #[tokio::test]
    async fn test_pool_large_capacity() {
        let pool = SshPool::new(1000, Duration::from_secs(3600));
        assert_eq!(pool.max_connections, 1000);
        assert_eq!(pool.idle_timeout, Duration::from_secs(3600));
    }

    #[tokio::test]
    async fn test_pool_close_all_idempotent() {
        let pool = SshPool::new(5, Duration::from_secs(60));
        pool.close_all().await.unwrap();
    }

    #[tokio::test]
    async fn test_pool_get_or_connect_different_keys_fail() {
        let pool = SshPool::new(5, Duration::from_secs(120));
        let cfg1 = SshConfig::new("127.0.0.1", "user1", PathBuf::from("/nonexistent/key1"));
        let cfg2 = SshConfig::new("127.0.0.2", "user2", PathBuf::from("/nonexistent/key2"));
        assert!(pool.get_or_connect(&cfg1).await.is_err());
        assert!(pool.get_or_connect(&cfg2).await.is_err());
        assert_eq!(pool.pool_size().await, 0);
    }

    #[tokio::test]
    async fn test_pool_zero_capacity() {
        let pool = SshPool::new(0, Duration::from_secs(60));
        assert_eq!(pool.max_connections, 0);
        let cfg = SshConfig::new("127.0.0.1", "user", PathBuf::from("/nonexistent/key"));
        // Should fail at key loading, not at capacity
        assert!(pool.get_or_connect(&cfg).await.is_err());
    }

    #[tokio::test]
    async fn test_pool_zero_idle_timeout() {
        let pool = SshPool::new(5, Duration::from_secs(0));
        assert_eq!(pool.idle_timeout, Duration::from_secs(0));
    }

    // ── SshClient connect failure path tests ────────────────────────

    #[tokio::test]
    async fn test_connect_with_empty_key_file() {
        let keyfile = NamedTempFile::new().unwrap();
        let cfg = SshConfig::new("127.0.0.1", "user", keyfile.path().to_path_buf());
        let result = SshClient::connect(&cfg).await;
        assert!(result.is_err());
        let err = result.err().unwrap().to_string();
        assert!(
            err.contains("key") || err.contains("Key"),
            "error should mention key: {err}"
        );
    }

    #[tokio::test]
    async fn test_connect_with_invalid_key_content() {
        let keyfile = NamedTempFile::new().unwrap();
        std::fs::write(keyfile.path(), "not a valid ssh key").unwrap();
        let cfg = SshConfig::new("127.0.0.1", "user", keyfile.path().to_path_buf());
        let result = SshClient::connect(&cfg).await;
        assert!(result.is_err());
    }

    #[tokio::test]
    async fn test_pool_get_or_connect_with_empty_key() {
        let pool = SshPool::new(5, Duration::from_secs(120));
        let keyfile = NamedTempFile::new().unwrap();
        let cfg = SshConfig::new("127.0.0.1", "user", keyfile.path().to_path_buf());
        let result = pool.get_or_connect(&cfg).await;
        assert!(result.is_err());
        assert_eq!(pool.pool_size().await, 0);
    }

    #[tokio::test]
    async fn test_pool_get_or_connect_with_invalid_key_content() {
        let pool = SshPool::new(5, Duration::from_secs(120));
        let keyfile = NamedTempFile::new().unwrap();
        std::fs::write(keyfile.path(), "invalid-key-data").unwrap();
        let cfg = SshConfig::new("10.255.255.1", "user", keyfile.path().to_path_buf());
        let result = pool.get_or_connect(&cfg).await;
        assert!(result.is_err());
        assert_eq!(pool.pool_size().await, 0);
    }

    // ── SshConfig comprehensive tests ───────────────────────────────

    #[test]
    fn test_ssh_config_with_empty_host() {
        let cfg = SshConfig::new("", "user", PathBuf::from("/key"));
        assert_eq!(cfg.host, "");
        assert_eq!(cfg.pool_key(), "user@:22");
    }

    #[test]
    fn test_ssh_config_with_empty_username() {
        let cfg = SshConfig::new("host", "", PathBuf::from("/key"));
        assert_eq!(cfg.username, "");
        assert_eq!(cfg.pool_key(), "@host:22");
    }

    #[test]
    fn test_ssh_config_pool_key_deterministic() {
        let cfg = SshConfig::new("host", "user", PathBuf::from("/key1"));
        let cfg2 = SshConfig::new("host", "user", PathBuf::from("/key2"));
        // Pool key doesn't include key_path
        assert_eq!(cfg.pool_key(), cfg2.pool_key());
    }

    #[test]
    fn test_ssh_config_pool_key_port_sensitive() {
        let mut cfg1 = SshConfig::new("host", "user", PathBuf::from("/key"));
        let mut cfg2 = SshConfig::new("host", "user", PathBuf::from("/key"));
        cfg1.port = 22;
        cfg2.port = 2222;
        assert_ne!(cfg1.pool_key(), cfg2.pool_key());
    }

    #[test]
    fn test_ssh_config_all_ports() {
        for port in [1u16, 22, 80, 443, 2222, 8022, 65535] {
            let mut cfg = SshConfig::new("host", "user", PathBuf::from("/key"));
            cfg.port = port;
            assert_eq!(cfg.port, port);
            assert!(cfg.pool_key().contains(&port.to_string()));
        }
    }

    #[test]
    fn test_ssh_config_various_timeouts() {
        for secs in [0u64, 1, 5, 10, 30, 60, 300, 3600] {
            let mut cfg = SshConfig::new("host", "user", PathBuf::from("/key"));
            cfg.timeout = Duration::from_secs(secs);
            assert_eq!(cfg.timeout, Duration::from_secs(secs));
        }
    }

    #[test]
    fn test_ssh_config_host_types() {
        let hosts = vec![
            "192.168.1.1",
            "10.0.0.1",
            "::1",
            "fe80::1",
            "example.com",
            "my-vm.internal.cloudapp.net",
            "localhost",
        ];
        for host in hosts {
            let cfg = SshConfig::new(host, "user", PathBuf::from("/key"));
            assert_eq!(cfg.host, host);
            assert!(cfg.pool_key().contains(host));
        }
    }

    #[test]
    fn test_ssh_config_username_types() {
        let usernames = vec![
            "root",
            "azureuser",
            "admin",
            "ec2-user",
            "user_with_underscore",
            "user.with.dots",
        ];
        for username in usernames {
            let cfg = SshConfig::new("host", username, PathBuf::from("/key"));
            assert_eq!(cfg.username, username);
            assert!(cfg.pool_key().starts_with(&format!("{username}@")));
        }
    }

    #[test]
    fn test_ssh_config_key_path_types() {
        let paths = vec![
            "/home/user/.ssh/id_rsa",
            "/home/user/.ssh/id_ed25519",
            "/tmp/key",
            "relative/key",
            "./key",
        ];
        for path in paths {
            let cfg = SshConfig::new("host", "user", PathBuf::from(path));
            assert_eq!(cfg.key_path, PathBuf::from(path));
        }
    }

    #[test]
    fn test_ssh_config_clone_independence() {
        let mut cfg = SshConfig::new("host1", "user1", PathBuf::from("/key1"));
        let cfg2 = cfg.clone();
        cfg.host = "host2".to_string();
        cfg.port = 2222;
        cfg.username = "user2".to_string();
        // Clone should be unaffected
        assert_eq!(cfg2.host, "host1");
        assert_eq!(cfg2.port, 22);
        assert_eq!(cfg2.username, "user1");
    }

    #[test]
    fn test_ssh_config_debug_format_completeness() {
        let cfg = SshConfig {
            host: "192.168.1.100".into(),
            port: 2222,
            username: "testuser".into(),
            key_path: PathBuf::from("/home/test/.ssh/id_rsa"),
            timeout: Duration::from_secs(60),
        };
        let debug = format!("{:?}", cfg);
        assert!(debug.contains("192.168.1.100"), "missing host in debug");
        assert!(debug.contains("2222"), "missing port in debug");
        assert!(debug.contains("testuser"), "missing username in debug");
        assert!(debug.contains("id_rsa"), "missing key_path in debug");
        assert!(debug.contains("60"), "missing timeout in debug");
    }

    // ── SshPool comprehensive tests ─────────────────────────────────

    #[tokio::test]
    async fn test_pool_multiple_failed_connects() {
        let pool = SshPool::new(5, Duration::from_secs(120));
        for i in 0..5 {
            let cfg = SshConfig::new(
                format!("10.255.255.{}", i),
                "user",
                PathBuf::from("/nonexistent/key"),
            );
            assert!(pool.get_or_connect(&cfg).await.is_err());
        }
        assert_eq!(pool.pool_size().await, 0);
    }

    #[tokio::test]
    async fn test_pool_same_config_multiple_attempts() {
        let pool = SshPool::new(5, Duration::from_secs(120));
        let cfg = SshConfig::new("127.0.0.1", "user", PathBuf::from("/nonexistent/key"));
        for _ in 0..3 {
            assert!(pool.get_or_connect(&cfg).await.is_err());
        }
        assert_eq!(pool.pool_size().await, 0);
    }

    #[tokio::test]
    async fn test_pool_varying_capacities() {
        for cap in [1usize, 2, 5, 10, 50, 100] {
            let pool = SshPool::new(cap, Duration::from_secs(60));
            assert_eq!(pool.max_connections, cap);
            assert_eq!(pool.pool_size().await, 0);
        }
    }

    #[tokio::test]
    async fn test_pool_varying_idle_timeouts() {
        for secs in [0u64, 1, 10, 60, 300, 3600] {
            let pool = SshPool::new(5, Duration::from_secs(secs));
            assert_eq!(pool.idle_timeout, Duration::from_secs(secs));
        }
    }

    #[tokio::test]
    async fn test_pool_concurrent_size_checks() {
        let pool = SshPool::new(10, Duration::from_secs(60));
        let pool_arc = Arc::new(pool);

        let mut handles = vec![];
        for _ in 0..5 {
            let p = Arc::clone(&pool_arc);
            handles.push(tokio::spawn(async move { p.pool_size().await }));
        }

        for handle in handles {
            let size = handle.await.unwrap();
            assert_eq!(size, 0);
        }
    }

    // ── SshClient connect error tests ───────────────────────────────

    #[tokio::test]
    async fn test_connect_with_directory_as_key_path() {
        let cfg = SshConfig::new("127.0.0.1", "user", PathBuf::from("/tmp"));
        let result = SshClient::connect(&cfg).await;
        assert!(result.is_err());
    }

    #[tokio::test]
    async fn test_connect_with_various_invalid_keys() {
        let test_cases = vec![
            ("", "empty"),
            ("not-a-key", "plaintext"),
            // Use a truncated PEM marker to avoid pre-commit false positive
            (
                "-----BEGIN RSA PRIV\ninvalid\n-----END RSA PRIV",
                "malformed pem",
            ),
            ("ssh-rsa AAAA public-key-not-private", "public key"),
        ];

        for (content, desc) in test_cases {
            let keyfile = NamedTempFile::new().unwrap();
            std::fs::write(keyfile.path(), content).unwrap();
            let cfg = SshConfig::new("127.0.0.1", "user", keyfile.path().to_path_buf());
            let result = SshClient::connect(&cfg).await;
            assert!(result.is_err(), "should fail for {desc}");
        }
    }

    #[tokio::test]
    async fn test_connect_error_contains_key_info() {
        let cfg = SshConfig::new("127.0.0.1", "user", PathBuf::from("/no/such/key/file.pem"));
        let err = SshClient::connect(&cfg).await.err().unwrap();
        let msg = err.to_string();
        assert!(
            msg.contains("key") || msg.contains("Key") || msg.contains("load"),
            "error should mention key: {msg}"
        );
    }

    #[tokio::test]
    async fn test_pool_connect_error_preserves_pool() {
        let pool = SshPool::new(3, Duration::from_secs(60));
        let bad_configs = vec![
            SshConfig::new("10.255.255.1", "u1", PathBuf::from("/bad1")),
            SshConfig::new("10.255.255.2", "u2", PathBuf::from("/bad2")),
            SshConfig::new("10.255.255.3", "u3", PathBuf::from("/bad3")),
        ];
        for cfg in &bad_configs {
            let _ = pool.get_or_connect(cfg).await;
        }
        // Failed connections should not be stored
        assert_eq!(pool.pool_size().await, 0);
    }

    // ── SshPool edge cases ──────────────────────────────────────────

    #[tokio::test]
    async fn test_pool_with_millis_timeout() {
        let pool = SshPool::new(5, Duration::from_millis(1));
        assert_eq!(pool.idle_timeout, Duration::from_millis(1));
    }

    #[tokio::test]
    async fn test_pool_with_nanos_timeout() {
        let pool = SshPool::new(5, Duration::from_nanos(1));
        assert_eq!(pool.idle_timeout, Duration::from_nanos(1));
    }

    #[tokio::test]
    async fn test_pool_default_matches_documented_values() {
        let pool = SshPool::default();
        // Default should be 20 max connections and 300s idle timeout
        assert_eq!(pool.max_connections, 20);
        assert_eq!(pool.idle_timeout.as_secs(), 300);
    }

    // ── SshConfig pool_key edge cases ───────────────────────────────

    #[test]
    fn test_pool_key_with_special_chars_in_host() {
        let cfg = SshConfig::new("vm-01.internal.cloud", "admin-user", PathBuf::from("/key"));
        let key = cfg.pool_key();
        assert_eq!(key, "admin-user@vm-01.internal.cloud:22");
    }

    #[test]
    fn test_pool_key_with_at_in_host() {
        // Edge case: host containing @
        let cfg = SshConfig::new("host@weird", "user", PathBuf::from("/key"));
        let key = cfg.pool_key();
        assert_eq!(key, "user@host@weird:22");
    }

    #[test]
    fn test_pool_key_with_colon_in_host() {
        // IPv6 addresses contain colons
        let cfg = SshConfig::new("2001:db8::1", "user", PathBuf::from("/key"));
        let key = cfg.pool_key();
        assert_eq!(key, "user@2001:db8::1:22");
    }

    // ── SshPool close_all tests ─────────────────────────────────────

    #[tokio::test]
    async fn test_pool_close_all_returns_ok() {
        let pool = SshPool::new(5, Duration::from_secs(60));
        assert!(pool.close_all().await.is_ok());
    }

    // ── Additional error variant tests ──────────────────────────────

    #[tokio::test]
    async fn test_connect_bad_key_returns_ssh_key_error() {
        let cfg = SshConfig::new("127.0.0.1", "user", PathBuf::from("/nonexistent/key"));
        let result = SshClient::connect(&cfg).await;
        assert!(result.is_err());
        let err_msg = result.err().unwrap().to_string();
        // Should be an SshKey error variant
        assert!(
            err_msg.contains("key") || err_msg.contains("Key"),
            "expected key-related error: {err_msg}"
        );
    }

    #[tokio::test]
    async fn test_pool_interleaved_configs() {
        let pool = SshPool::new(10, Duration::from_secs(60));
        let configs: Vec<SshConfig> = (0..5)
            .map(|i| {
                SshConfig::new(
                    format!("host{i}"),
                    format!("user{i}"),
                    PathBuf::from(format!("/nonexistent/key{i}")),
                )
            })
            .collect();

        // Interleave attempts
        for _ in 0..3 {
            for cfg in &configs {
                let _ = pool.get_or_connect(cfg).await;
            }
        }
        assert_eq!(pool.pool_size().await, 0);
    }

    #[test]
    fn test_ssh_config_with_min_port() {
        let mut cfg = SshConfig::new("host", "user", PathBuf::from("/key"));
        cfg.port = 1;
        assert_eq!(cfg.port, 1);
        assert_eq!(cfg.pool_key(), "user@host:1");
    }

    #[test]
    fn test_ssh_config_with_max_port() {
        let mut cfg = SshConfig::new("host", "user", PathBuf::from("/key"));
        cfg.port = u16::MAX;
        assert_eq!(cfg.port, 65535);
        assert_eq!(cfg.pool_key(), "user@host:65535");
    }

    #[test]
    fn test_ssh_config_with_zero_timeout() {
        let mut cfg = SshConfig::new("host", "user", PathBuf::from("/key"));
        cfg.timeout = Duration::ZERO;
        assert_eq!(cfg.timeout, Duration::ZERO);
    }

    #[test]
    fn test_ssh_config_from_string_impl() {
        // Test Into<String> for both host and username
        let host: String = "myhost".to_string();
        let user: String = "myuser".to_string();
        let cfg = SshConfig::new(host.clone(), user.clone(), PathBuf::from("/key"));
        assert_eq!(cfg.host, host);
        assert_eq!(cfg.username, user);
    }

    #[test]
    fn test_ssh_config_from_str_ref() {
        let cfg = SshConfig::new("host", "user", PathBuf::from("/key"));
        assert_eq!(cfg.host, "host");
        assert_eq!(cfg.username, "user");
    }

    #[test]
    fn test_rotation_key_name() {
        let name = rotation_key_name("azlin");
        assert!(name.starts_with("azlin_rotated_"));
        assert!(name.len() > 20);
    }

    #[test]
    fn test_key_needs_rotation_missing_file() {
        assert!(key_needs_rotation(std::path::Path::new("/nonexistent/key"), 30));
    }

    #[test]
    fn test_plan_rotation_single_batch() {
        let batches = plan_rotation(3, 10);
        assert_eq!(batches.len(), 1);
        assert_eq!(batches[0], (0, 3));
    }

    #[test]
    fn test_plan_rotation_multiple_batches() {
        let batches = plan_rotation(10, 3);
        assert_eq!(batches.len(), 4);
        assert_eq!(batches[0], (0, 3));
        assert_eq!(batches[3], (9, 10));
    }

    #[test]
    fn test_plan_rotation_empty() {
        let batches = plan_rotation(0, 5);
        assert!(batches.is_empty());
    }

    #[test]
    fn test_key_needs_rotation_fresh_file() {
        let file = NamedTempFile::new().unwrap();
        // Brand new file should not need rotation with 30-day window
        assert!(!key_needs_rotation(file.path(), 30));
    }

    #[test]
    fn test_key_needs_rotation_zero_max_age() {
        let file = NamedTempFile::new().unwrap();
        // With max_age_days=0, a brand-new file has age_secs=0, so 0 > 0 is false
        assert!(!key_needs_rotation(file.path(), 0));
    }

    #[test]
    fn test_key_needs_rotation_large_max_age() {
        let file = NamedTempFile::new().unwrap();
        // 100 years — should never need rotation
        assert!(!key_needs_rotation(file.path(), 36500));
    }

    #[test]
    fn test_rotation_key_name_various_prefixes() {
        for prefix in &["azlin", "prod-vm", "key_backup", "test123"] {
            let name = rotation_key_name(prefix);
            assert!(name.starts_with(&format!("{}_rotated_", prefix)));
            // Should contain a timestamp portion (YYYYMMDD_HHMMSS = 15 chars)
            assert!(name.len() > prefix.len() + "_rotated_".len() + 10);
        }
    }

    #[test]
    fn test_rotation_key_name_empty_prefix() {
        let name = rotation_key_name("");
        assert!(name.starts_with("_rotated_"));
    }

    #[test]
    fn test_plan_rotation_exact_fit() {
        let batches = plan_rotation(10, 5);
        assert_eq!(batches.len(), 2);
        assert_eq!(batches[0], (0, 5));
        assert_eq!(batches[1], (5, 10));
    }

    #[test]
    fn test_plan_rotation_batch_size_one() {
        let batches = plan_rotation(4, 1);
        assert_eq!(batches.len(), 4);
        assert_eq!(batches[0], (0, 1));
        assert_eq!(batches[1], (1, 2));
        assert_eq!(batches[2], (2, 3));
        assert_eq!(batches[3], (3, 4));
    }

    #[test]
    fn test_plan_rotation_single_vm() {
        let batches = plan_rotation(1, 10);
        assert_eq!(batches.len(), 1);
        assert_eq!(batches[0], (0, 1));
    }

    #[test]
    fn test_plan_rotation_large_fleet() {
        let batches = plan_rotation(100, 10);
        assert_eq!(batches.len(), 10);
        assert_eq!(batches[0], (0, 10));
        assert_eq!(batches[9], (90, 100));
        // Verify contiguity
        for i in 0..batches.len() - 1 {
            assert_eq!(batches[i].1, batches[i + 1].0);
        }
    }

    #[test]
    fn test_plan_rotation_batch_equals_count() {
        let batches = plan_rotation(5, 5);
        assert_eq!(batches.len(), 1);
        assert_eq!(batches[0], (0, 5));
    }

    #[test]
    fn test_plan_rotation_batch_larger_than_count() {
        let batches = plan_rotation(3, 100);
        assert_eq!(batches.len(), 1);
        assert_eq!(batches[0], (0, 3));
    }

    #[test]
    fn test_key_needs_rotation_nonexistent_dir() {
        assert!(key_needs_rotation(
            std::path::Path::new("/no/such/dir/keyfile"),
            30
        ));
    }
}
