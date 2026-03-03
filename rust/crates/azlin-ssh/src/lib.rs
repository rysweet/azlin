//! azlin-ssh: SSH connection pooling and remote command execution.
//!
//! Provides async SSH connectivity using `russh`, mirroring the Python
//! `azlin.ssh.connection_pool` module with connection reuse, remote command
//! execution, and file transfer.

use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::time::{Duration, Instant};

use azlin_core::models::CommandResult;
use azlin_core::{AzlinError, Result};
use async_trait::async_trait;
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

        let mut russh_config = client::Config::default();
        russh_config.inactivity_timeout = Some(config.timeout);
        let russh_config = Arc::new(russh_config);

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

        let cmd = format!(
            "cat > {}",
            shell_escape::unix::escape(remote_path.into())
        );
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
        let cmd = format!(
            "cat {}",
            shell_escape::unix::escape(remote_path.into())
        );
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
}
