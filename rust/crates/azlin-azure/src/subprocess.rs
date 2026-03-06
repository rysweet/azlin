//! Shared subprocess execution with timeout and pipe-deadlock prevention.
//!
//! Extracted from the duplicated drain-before-wait pattern that appeared in
//! `vm.rs`, `auth.rs`, `main.rs`, and `display_helpers.rs`.

use anyhow::{Context, Result};
use wait_timeout::ChildExt;

/// Run a subprocess with timeout and pipe-deadlock prevention.
///
/// Spawns `cmd` with the given `args`, draining stdout and stderr in background
/// threads to prevent the classic pipe-buffer deadlock (child blocks writing to
/// a full pipe while we block waiting for exit).
///
/// Returns `(exit_code, stdout, stderr)` on completion.
/// Returns `Err` on spawn failure or timeout.
pub fn run_with_timeout(
    cmd: &str,
    args: &[&str],
    timeout_secs: u64,
) -> Result<(i32, String, String)> {
    let mut child = std::process::Command::new(cmd)
        .args(args)
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::piped())
        .spawn()
        .context(format!("Failed to execute '{}'", cmd))?;

    let stdout_handle = child.stdout.take().map(|mut pipe| {
        std::thread::spawn(move || {
            let mut buf = Vec::new();
            std::io::Read::read_to_end(&mut pipe, &mut buf).ok();
            buf
        })
    });
    let stderr_handle = child.stderr.take().map(|mut pipe| {
        std::thread::spawn(move || {
            let mut buf = Vec::new();
            std::io::Read::read_to_end(&mut pipe, &mut buf).ok();
            buf
        })
    });

    let timeout = std::time::Duration::from_secs(timeout_secs);
    match child.wait_timeout(timeout) {
        Ok(Some(status)) => {
            let stdout = stdout_handle
                .and_then(|h| h.join().ok())
                .unwrap_or_default();
            let stderr = stderr_handle
                .and_then(|h| h.join().ok())
                .unwrap_or_default();
            Ok((
                status.code().unwrap_or(-1),
                String::from_utf8_lossy(&stdout).to_string(),
                String::from_utf8_lossy(&stderr).to_string(),
            ))
        }
        Ok(None) => {
            let _ = child.kill();
            let _ = child.wait();
            Err(anyhow::anyhow!("{} timed out after {}s", cmd, timeout_secs))
        }
        Err(e) => Err(anyhow::anyhow!("Failed to wait for {}: {}", cmd, e)),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_run_with_timeout_echo() {
        let (code, stdout, _stderr) = run_with_timeout("echo", &["hello"], 10).unwrap();
        assert_eq!(code, 0);
        assert_eq!(stdout.trim(), "hello");
    }

    #[test]
    fn test_run_with_timeout_nonexistent_command() {
        let result = run_with_timeout("this_command_does_not_exist_xyz", &[], 10);
        assert!(result.is_err());
        let msg = result.unwrap_err().to_string();
        assert!(
            msg.contains("Failed to execute"),
            "error should mention spawn failure: {msg}"
        );
    }

    #[test]
    fn test_run_with_timeout_captures_stderr() {
        // `ls` on a nonexistent path should produce stderr and nonzero exit
        let result = run_with_timeout("ls", &["/nonexistent_path_xyz_123"], 10);
        match result {
            Ok((code, _stdout, stderr)) => {
                assert_ne!(code, 0);
                assert!(
                    !stderr.is_empty(),
                    "stderr should contain error message"
                );
            }
            Err(_) => {
                // Some systems may not have `ls`, that's fine
            }
        }
    }

    #[test]
    fn test_run_with_timeout_returns_exit_code() {
        let (code, _, _) = run_with_timeout("false", &[], 10).unwrap();
        assert_ne!(code, 0);
    }
}
