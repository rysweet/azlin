//! Handler functions split from the monolithic handlers.rs.
#![allow(dead_code)]

// ── Autopilot handlers ──────────────────────────────────────────────────

/// Build the autopilot TOML config table.
pub fn build_autopilot_config(
    budget: Option<u32>,
    strategy: &str,
    idle_threshold: u32,
    cpu_threshold: u32,
    timestamp: &str,
) -> toml::Value {
    let mut config = toml::map::Map::new();
    config.insert("enabled".to_string(), toml::Value::Boolean(true));
    if let Some(b) = budget {
        config.insert("budget".to_string(), toml::Value::Integer(b as i64));
    }
    config.insert(
        "strategy".to_string(),
        toml::Value::String(strategy.to_string()),
    );
    config.insert(
        "idle_threshold_minutes".to_string(),
        toml::Value::Integer(idle_threshold as i64),
    );
    config.insert(
        "cpu_threshold_percent".to_string(),
        toml::Value::Integer(cpu_threshold as i64),
    );
    config.insert(
        "updated".to_string(),
        toml::Value::String(timestamp.to_string()),
    );
    toml::Value::Table(config)
}

/// Format the autopilot enable output message.
pub fn format_autopilot_enabled(
    budget: Option<u32>,
    strategy: &str,
    idle_threshold: u32,
    cpu_threshold: u32,
) -> String {
    let mut out = "Autopilot enabled:\n".to_string();
    if let Some(b) = budget {
        out.push_str(&format!("  Budget:         ${}/month\n", b));
    }
    out.push_str(&format!("  Strategy:       {}\n", strategy));
    out.push_str(&format!("  Idle threshold: {} min\n", idle_threshold));
    out.push_str(&format!("  CPU threshold:  {}%", cpu_threshold));
    out
}

/// Format the autopilot status output from a parsed TOML value.
pub fn format_autopilot_status(config: Option<&toml::Value>) -> String {
    match config {
        Some(val) => {
            if let Some(t) = val.as_table() {
                let enabled = t.get("enabled").and_then(|v| v.as_bool()).unwrap_or(false);
                let mut out = format!(
                    "Autopilot: {}",
                    if enabled { "ENABLED" } else { "DISABLED" }
                );
                for (k, v) in t {
                    if k != "enabled" {
                        out.push_str(&format!("\n  {}: {}", k, v));
                    }
                }
                out
            } else {
                "Autopilot: invalid configuration".to_string()
            }
        }
        None => "Autopilot: not configured\nEnable with: azlin autopilot enable".to_string(),
    }
}

/// Parse autopilot config to get thresholds.
pub fn parse_autopilot_thresholds(config: Option<&toml::Value>) -> (u32, f64) {
    match config {
        Some(val) => {
            let thresh = val
                .as_table()
                .and_then(|t| t.get("idle_threshold_minutes"))
                .and_then(|v| v.as_integer())
                .unwrap_or(30) as u32;
            let limit = val
                .as_table()
                .and_then(|t| t.get("cost_limit_usd"))
                .and_then(|v| v.as_float())
                .unwrap_or(0.0);
            (thresh, limit)
        }
        None => (30, 0.0),
    }
}

/// Classify a VM's CPU/uptime into an autopilot action recommendation.
/// Returns Some(action_name) if an action is recommended, None if VM is active.
pub fn classify_autopilot_vm(
    cpu_pct: f64,
    uptime_secs: f64,
    idle_threshold_minutes: u32,
) -> Option<String> {
    let idle_mins = idle_threshold_minutes as f64;
    if cpu_pct < 5.0 && uptime_secs > idle_mins * 60.0 {
        Some("deallocate".to_string())
    } else {
        None
    }
}

/// Format autopilot dry-run report.
pub fn format_autopilot_dry_run(actions: &[(String, String)]) -> String {
    let mut out = format!("\nDry run — {} action(s) would be taken:", actions.len());
    for (name, action) in actions {
        out.push_str(&format!("\n  {} -> {}", name, action));
    }
    out
}
