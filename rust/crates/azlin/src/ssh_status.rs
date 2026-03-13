//! SSH status bar: displays a persistent information line above the SSH session.
//!
//! Instead of wrapping the SSH PTY (which is fragile and interferes with terminal
//! features), we display a status line BEFORE launching SSH and set the terminal
//! title to show connection info persistently. The SSH process gets the full
//! terminal unmodified.

use console::Style;

/// Connection info displayed in the status bar.
pub struct SshConnectionInfo {
    pub vm_name: String,
    pub ip: String,
    pub user: String,
    pub via_bastion: bool,
}

/// Print a status banner before SSH connection and set terminal title.
///
/// This approach works reliably with all terminal emulators and does not
/// interfere with the SSH session (unlike PTY wrapping with ratatui).
pub fn display_ssh_status(info: &SshConnectionInfo) {
    let bold = Style::new().bold();
    let cyan = Style::new().cyan();
    let dim = Style::new().dim();
    let green = Style::new().green();

    let route = if info.via_bastion {
        " (via bastion)"
    } else {
        ""
    };

    // Print a compact status bar
    eprintln!(
        "{} {} {}@{}{} {}",
        green.apply_to(">>>"),
        bold.apply_to("azlin connect"),
        cyan.apply_to(&info.user),
        cyan.apply_to(&info.ip),
        dim.apply_to(route),
        dim.apply_to(format!("[{}]", info.vm_name)),
    );

    // Set terminal title via ANSI escape (works in xterm, iTerm2, Windows Terminal, etc.)
    eprint!(
        "\x1b]0;azlin: {}@{} ({}){}\x07",
        info.user, info.ip, info.vm_name, route
    );
}

/// Restore terminal title after SSH disconnects.
pub fn clear_ssh_status() {
    // Reset terminal title
    eprint!("\x1b]0;\x07");
    eprintln!();
}

/// Format a duration in seconds as a human-readable uptime string.
pub fn format_uptime(seconds: u64) -> String {
    let hours = seconds / 3600;
    let minutes = (seconds % 3600) / 60;
    if hours > 0 {
        format!("{}h {}m", hours, minutes)
    } else {
        format!("{}m", minutes)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_format_uptime_minutes_only() {
        assert_eq!(format_uptime(300), "5m");
        assert_eq!(format_uptime(0), "0m");
        assert_eq!(format_uptime(59), "0m");
    }

    #[test]
    fn test_format_uptime_hours_and_minutes() {
        assert_eq!(format_uptime(3600), "1h 0m");
        assert_eq!(format_uptime(3661), "1h 1m");
        assert_eq!(format_uptime(7200), "2h 0m");
    }

    #[test]
    fn test_connection_info_struct() {
        let info = SshConnectionInfo {
            vm_name: "test-vm".to_string(),
            ip: "10.0.0.1".to_string(),
            user: "azureuser".to_string(),
            via_bastion: false,
        };
        assert_eq!(info.vm_name, "test-vm");
        assert!(!info.via_bastion);
    }

    #[test]
    fn test_connection_info_bastion() {
        let info = SshConnectionInfo {
            vm_name: "private-vm".to_string(),
            ip: "10.0.0.5".to_string(),
            user: "admin".to_string(),
            via_bastion: true,
        };
        assert!(info.via_bastion);
    }
}
