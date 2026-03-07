/// Pick a colour name for a utilisation percentage.
#[allow(dead_code)]
pub fn metric_color(pct: f32) -> &'static str {
    if pct > 80.0 {
        "red"
    } else if pct > 50.0 {
        "yellow"
    } else {
        "green"
    }
}

/// Pick a colour name for a VM power-state string.
#[allow(dead_code)]
pub fn state_color(state: &str) -> &'static str {
    match state {
        "running" => "green",
        "stopped" | "deallocated" => "red",
        _ => "yellow",
    }
}

/// Format a metric value as `"xx.x%"`, clamping negatives to 0.
pub fn format_percentage(value: f32) -> String {
    let clamped = if value < 0.0 { 0.0 } else { value };
    format!("{:.1}%", clamped)
}

/// Return a status emoji summarising overall health.
#[allow(dead_code)]
pub fn status_emoji(cpu: f32, mem: f32, disk: f32) -> &'static str {
    if cpu > 90.0 || mem > 90.0 || disk > 90.0 {
        "🔴"
    } else if cpu > 70.0 || mem > 70.0 || disk > 70.0 {
        "🟡"
    } else {
        "🟢"
    }
}
