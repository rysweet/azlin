//! Handler functions split from the monolithic handlers.rs.
#![allow(dead_code)]

// ── Context handlers ────────────────────────────────────────────────────

/// Format context list output for table display.
pub fn format_context_list_table(contexts: &[(String, bool)]) -> String {
    let mut out = String::new();
    for (name, is_active) in contexts {
        if *is_active {
            out.push_str(&format!("* {}\n", name));
        } else {
            out.push_str(&format!("  {}\n", name));
        }
    }
    out
}

/// Format the "no contexts" message.
pub fn format_no_contexts() -> &'static str {
    "No contexts found. Create one with: azlin context create <name>"
}

/// Format the context show output.
pub fn format_context_show(name: &str, content: Option<&str>) -> String {
    let mut out = format!("Current context: {}", name);
    if let Some(c) = content {
        out.push_str(&format!("\n{}", c.trim()));
    }
    out
}

/// Format the context switch message.
pub fn format_context_switched(name: &str) -> String {
    format!("Switched to context '{}'", name)
}

/// Format the context create message.
pub fn format_context_created(name: &str) -> String {
    format!("Created context '{}'", name)
}

/// Format the context delete message.
pub fn format_context_deleted(name: &str) -> String {
    format!("Deleted context '{}'", name)
}

/// Format the context rename message.
pub fn format_context_renamed(old_name: &str, new_name: &str) -> String {
    format!("Renamed context '{}' -> '{}'", old_name, new_name)
}
