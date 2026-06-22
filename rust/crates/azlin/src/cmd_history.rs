use anyhow::{Context, Result};
use chrono::{DateTime, Local, Utc};
use console::Style;
use serde::{Deserialize, Serialize};
use std::io::{BufRead, Write};
use std::path::PathBuf;

/// Maximum number of history entries to keep.
const MAX_HISTORY_ENTRIES: usize = 500;

/// Sensitive argument patterns to redact in history.
const SENSITIVE_PATTERNS: &[&str] = &[
    "--token",
    "--secret",
    "--password",
    "--api-key",
    "--client-secret",
];

/// A single command history entry.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct HistoryEntry {
    pub command: String,
    pub timestamp: DateTime<Utc>,
    pub exit_code: Option<i32>,
}

/// Handle `azlin history` commands.
pub(crate) fn handle_history(action: Option<azlin_cli::HistoryAction>, count: u32) -> Result<()> {
    match action {
        Some(azlin_cli::HistoryAction::Clear) => {
            clear_history()?;
            println!("History cleared.");
        }
        Some(azlin_cli::HistoryAction::Replay { index }) => {
            replay_command(index)?;
        }
        None => {
            show_history(count)?;
        }
    }
    Ok(())
}

/// Record a command execution to the history file.
pub(crate) fn record_command(args: &[String], exit_code: Option<i32>) {
    // Respect --no-history flag and AZLIN_NO_HISTORY env var
    if std::env::var("AZLIN_NO_HISTORY").is_ok() {
        return;
    }

    let command = redact_sensitive_args(args);
    let entry = HistoryEntry {
        command,
        timestamp: Utc::now(),
        exit_code,
    };

    if let Err(e) = append_entry(&entry) {
        tracing::debug!("Failed to record history: {}", e);
    }
}

/// Show recent command history.
fn show_history(count: u32) -> Result<()> {
    let entries = load_history()?;
    let bold = Style::new().bold();
    let dim = Style::new().dim();
    let cyan = Style::new().cyan();

    if entries.is_empty() {
        println!("No command history yet.");
        return Ok(());
    }

    let start = entries.len().saturating_sub(count as usize);
    let recent = &entries[start..];

    for (display_idx, entry) in recent.iter().enumerate() {
        let idx = start + display_idx + 1;
        let ago = format_time_ago(entry.timestamp);
        let status = match entry.exit_code {
            Some(0) => String::new(),
            Some(code) => format!(" [exit {}]", code),
            None => String::new(),
        };

        println!(
            "  {}  {}  {}{}",
            bold.apply_to(format!("{:>4}", idx)),
            cyan.apply_to(&entry.command),
            dim.apply_to(format!("({})", ago)),
            dim.apply_to(status),
        );
    }
    Ok(())
}

/// Replay a command from history by its index.
fn replay_command(index: u32) -> Result<()> {
    let entries = load_history()?;

    if index == 0 || index as usize > entries.len() {
        anyhow::bail!(
            "Invalid history index {}. Valid range: 1-{}",
            index,
            entries.len()
        );
    }

    let entry = &entries[index as usize - 1];
    println!("Replaying: {}", entry.command);

    // Parse the stored command string back into arguments
    let parts: Vec<String> = match shlex::split(&entry.command) {
        Some(p) => p,
        None => {
            anyhow::bail!("Failed to parse command: {}", entry.command);
        }
    };

    if parts.is_empty() {
        anyhow::bail!("Empty command");
    }

    // Skip "azlin" prefix if present
    let args = if parts[0] == "azlin" {
        &parts[1..]
    } else {
        &parts
    };

    let status = std::process::Command::new("azlin")
        .args(args)
        .status()
        .context("Failed to execute command")?;

    std::process::exit(status.code().unwrap_or(1));
}

/// Clear all command history.
fn clear_history() -> Result<()> {
    let path = history_path()?;
    if path.exists() {
        std::fs::remove_file(&path)?;
    }
    Ok(())
}

/// Get the history file path.
fn history_path() -> Result<PathBuf> {
    let config_dir = azlin_core::AzlinConfig::config_dir()?;
    Ok(config_dir.join("history"))
}

/// Load all history entries from the file.
fn load_history() -> Result<Vec<HistoryEntry>> {
    let path = history_path()?;
    if !path.exists() {
        return Ok(Vec::new());
    }

    let file = std::fs::File::open(&path)?;
    let reader = std::io::BufReader::new(file);
    let mut entries = Vec::new();

    for line in reader.lines() {
        let line = line?;
        if let Ok(entry) = serde_json::from_str::<HistoryEntry>(&line) {
            entries.push(entry);
        }
    }

    Ok(entries)
}

/// Append a single entry to the history file (JSON lines format).
fn append_entry(entry: &HistoryEntry) -> Result<()> {
    let path = history_path()?;

    // Create config directory if needed
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
    }

    // Check if rotation is needed
    let needs_rotation = path.exists() && {
        let file = std::fs::File::open(&path)?;
        let count = std::io::BufReader::new(file).lines().count();
        count >= MAX_HISTORY_ENTRIES
    };

    if needs_rotation {
        rotate_history(&path)?;
    }

    let mut file = std::fs::OpenOptions::new()
        .create(true)
        .append(true)
        .open(&path)?;

    let json = serde_json::to_string(entry)?;
    writeln!(file, "{}", json)?;

    Ok(())
}

/// Rotate history by keeping only the most recent half of entries.
fn rotate_history(path: &PathBuf) -> Result<()> {
    let entries = load_history()?;
    let keep_from = entries.len() / 2;
    let to_keep = &entries[keep_from..];

    let tmp_path = path.with_extension("tmp");
    {
        let mut file = std::fs::File::create(&tmp_path)?;
        for entry in to_keep {
            let json = serde_json::to_string(entry)?;
            writeln!(file, "{}", json)?;
        }
    }
    std::fs::rename(&tmp_path, path)?;

    Ok(())
}

/// Redact sensitive argument values from a command.
fn redact_sensitive_args(args: &[String]) -> String {
    let mut result = Vec::new();
    let mut skip_next = false;

    for arg in args {
        if skip_next {
            result.push("***".to_string());
            skip_next = false;
            continue;
        }

        let lower = arg.to_lowercase();
        if SENSITIVE_PATTERNS.iter().any(|p| lower.starts_with(p)) {
            if arg.contains('=') {
                // --token=VALUE format
                let prefix = arg.split('=').next().unwrap();
                result.push(format!("{}=***", prefix));
            } else {
                // --token VALUE format
                result.push(arg.clone());
                skip_next = true;
            }
        } else {
            result.push(arg.clone());
        }
    }

    result.join(" ")
}

/// Format a UTC timestamp as a human-readable "time ago" string.
fn format_time_ago(timestamp: DateTime<Utc>) -> String {
    let now = Utc::now();
    let duration = now.signed_duration_since(timestamp);

    let seconds = duration.num_seconds();
    if seconds < 60 {
        return "just now".to_string();
    }
    let minutes = duration.num_minutes();
    if minutes < 60 {
        return format!("{} min ago", minutes);
    }
    let hours = duration.num_hours();
    if hours < 24 {
        return format!("{} hours ago", hours);
    }
    let days = duration.num_days();
    if days == 1 {
        return "yesterday".to_string();
    }
    if days < 30 {
        return format!("{} days ago", days);
    }

    // Fall back to local date
    let local: DateTime<Local> = timestamp.into();
    local.format("%Y-%m-%d").to_string()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_redact_sensitive_args_token_eq() {
        let args = vec![
            "azlin".to_string(),
            "--token=secret123".to_string(),
            "list".to_string(),
        ];
        let result = redact_sensitive_args(&args);
        assert!(result.contains("--token=***"));
        assert!(!result.contains("secret123"));
    }

    #[test]
    fn test_redact_sensitive_args_token_space() {
        let args = vec![
            "azlin".to_string(),
            "--token".to_string(),
            "secret123".to_string(),
            "list".to_string(),
        ];
        let result = redact_sensitive_args(&args);
        assert!(result.contains("--token ***"));
        assert!(!result.contains("secret123"));
    }

    #[test]
    fn test_redact_no_sensitive() {
        let args = vec![
            "azlin".to_string(),
            "list".to_string(),
            "--status".to_string(),
            "active".to_string(),
        ];
        let result = redact_sensitive_args(&args);
        assert_eq!(result, "azlin list --status active");
    }

    #[test]
    fn test_format_time_ago_just_now() {
        let now = Utc::now();
        assert_eq!(format_time_ago(now), "just now");
    }

    #[test]
    fn test_format_time_ago_minutes() {
        let five_min_ago = Utc::now() - chrono::Duration::minutes(5);
        assert_eq!(format_time_ago(five_min_ago), "5 min ago");
    }

    #[test]
    fn test_format_time_ago_hours() {
        let two_hours_ago = Utc::now() - chrono::Duration::hours(2);
        assert_eq!(format_time_ago(two_hours_ago), "2 hours ago");
    }

    #[test]
    fn test_format_time_ago_yesterday() {
        let yesterday = Utc::now() - chrono::Duration::days(1);
        assert_eq!(format_time_ago(yesterday), "yesterday");
    }

    #[test]
    fn test_history_path() {
        let path = history_path();
        assert!(path.is_ok());
        let p = path.unwrap();
        assert!(p.file_name().unwrap() == "history");
    }

    #[test]
    fn test_history_entry_serde_roundtrip() {
        let entry = HistoryEntry {
            command: "azlin list --status active".to_string(),
            timestamp: Utc::now(),
            exit_code: Some(0),
        };
        let json = serde_json::to_string(&entry).unwrap();
        let loaded: HistoryEntry = serde_json::from_str(&json).unwrap();
        assert_eq!(loaded.command, entry.command);
        assert_eq!(loaded.exit_code, entry.exit_code);
    }
}
