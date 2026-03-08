//! Handler functions split from the monolithic handlers.rs.
#![allow(dead_code)]

// ── Help handler ──────────────────────────────────────────────────────

/// Build extended help text for a given command (or general help if None).
pub fn build_extended_help(command_name: Option<&str>) -> String {
    match command_name {
        Some(cmd) => {
            let mut out = format!("azlin {} -- Extended help\n\n", cmd);
            out.push_str(&format!("Run 'azlin {} --help' for usage details.", cmd));
            out
        }
        None => {
            let mut out = String::from("azlin -- Azure VM fleet management CLI\n\n");
            out.push_str("Run 'azlin --help' for a list of commands.\n");
            out.push_str("Run 'azlin <command> --help' for command-specific help.\n\n");
            out.push_str("Tip: Generate shell completions with:\n");
            out.push_str("  azlin completions bash >> ~/.bashrc\n");
            out.push_str("  azlin completions zsh  >> ~/.zshrc\n");
            out.push_str("  azlin completions fish >  ~/.config/fish/completions/azlin.fish\n");
            out
        }
    }
}
