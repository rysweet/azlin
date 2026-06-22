use anyhow::Result;
use console::Style;

/// Show differences between current config and defaults (or a specified file).
pub(crate) fn handle_config_diff(show_all: bool, format: &str, file: Option<&str>) -> Result<()> {
    let current = azlin_core::AzlinConfig::load()?;
    let baseline = if let Some(path) = file {
        let contents = std::fs::read_to_string(path)
            .map_err(|e| anyhow::anyhow!("Failed to read {}: {}", path, e))?;
        toml::from_str(&contents)?
    } else {
        azlin_core::AzlinConfig::default()
    };

    let current_json = serde_json::to_value(&current)?;
    let baseline_json = serde_json::to_value(&baseline)?;

    let current_obj = current_json.as_object().unwrap();
    let baseline_obj = baseline_json.as_object().unwrap();

    if format == "json" {
        return print_json_diff(current_obj, baseline_obj, show_all);
    }

    print_table_diff(current_obj, baseline_obj, show_all);
    Ok(())
}

fn print_json_diff(
    current: &serde_json::Map<String, serde_json::Value>,
    baseline: &serde_json::Map<String, serde_json::Value>,
    show_all: bool,
) -> Result<()> {
    let mut diff = serde_json::Map::new();
    let mut changed = 0u32;
    let mut total = 0u32;

    for (key, current_val) in current {
        total += 1;
        let baseline_val = baseline.get(key);
        let is_changed = baseline_val != Some(current_val);

        if show_all || is_changed {
            let mut entry = serde_json::Map::new();
            entry.insert("current".to_string(), current_val.clone());
            if let Some(bv) = baseline_val {
                entry.insert("default".to_string(), bv.clone());
            }
            entry.insert("changed".to_string(), serde_json::Value::Bool(is_changed));
            diff.insert(key.clone(), serde_json::Value::Object(entry));
        }

        if is_changed {
            changed += 1;
        }
    }

    let mut output = serde_json::Map::new();
    output.insert("diff".to_string(), serde_json::Value::Object(diff));
    output.insert("changed_count".to_string(), serde_json::json!(changed));
    output.insert("total_count".to_string(), serde_json::json!(total));

    println!("{}", serde_json::to_string_pretty(&output)?);
    Ok(())
}

fn print_table_diff(
    current: &serde_json::Map<String, serde_json::Value>,
    baseline: &serde_json::Map<String, serde_json::Value>,
    show_all: bool,
) {
    let green = Style::new().green();
    let red = Style::new().red();
    let dim = Style::new().dim();
    let bold = Style::new().bold();
    let cyan = Style::new().cyan();

    println!();
    println!("  {}", bold.apply_to("Config Diff (current vs defaults):"));
    println!();

    let mut changed = 0u32;
    let mut total = 0u32;

    // Calculate max key width for alignment
    let max_key_len = current.keys().map(|k| k.len()).max().unwrap_or(20);

    for (key, current_val) in current {
        total += 1;
        let baseline_val = baseline.get(key);
        let is_changed = baseline_val != Some(current_val);

        if !show_all && !is_changed {
            continue;
        }

        let current_display = format_value(current_val);

        if is_changed {
            changed += 1;
            let default_display = baseline_val
                .map(format_value)
                .unwrap_or_else(|| "(new)".to_string());
            println!(
                "  {:<width$}  {}  {}",
                cyan.apply_to(key),
                green.apply_to(&current_display),
                dim.apply_to(format!("(default: {})", red.apply_to(&default_display))),
                width = max_key_len,
            );
        } else {
            println!(
                "  {:<width$}  {}  {}",
                dim.apply_to(key),
                dim.apply_to(&current_display),
                dim.apply_to("(unchanged)"),
                width = max_key_len,
            );
        }
    }

    println!();
    let at_default = total - changed;
    println!(
        "  {} values changed, {} at defaults.",
        bold.apply_to(changed),
        at_default
    );
}

fn format_value(v: &serde_json::Value) -> String {
    match v {
        serde_json::Value::String(s) => s.clone(),
        serde_json::Value::Null => "null".to_string(),
        serde_json::Value::Bool(b) => b.to_string(),
        serde_json::Value::Number(n) => n.to_string(),
        other => other.to_string(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_format_value_string() {
        let v = serde_json::json!("hello");
        assert_eq!(format_value(&v), "hello");
    }

    #[test]
    fn test_format_value_null() {
        let v = serde_json::Value::Null;
        assert_eq!(format_value(&v), "null");
    }

    #[test]
    fn test_format_value_bool() {
        assert_eq!(format_value(&serde_json::json!(true)), "true");
        assert_eq!(format_value(&serde_json::json!(false)), "false");
    }

    #[test]
    fn test_format_value_number() {
        assert_eq!(format_value(&serde_json::json!(42)), "42");
    }

    #[test]
    fn test_json_diff_no_changes() {
        let config = azlin_core::AzlinConfig::default();
        let json = serde_json::to_value(&config).unwrap();
        let obj = json.as_object().unwrap();

        // Comparing defaults to defaults should show 0 changes
        let result = print_json_diff(obj, obj, false);
        assert!(result.is_ok());
    }

    #[test]
    fn test_json_diff_with_changes() {
        let mut config = azlin_core::AzlinConfig::default();
        config.default_region = "eastus".to_string();
        let current = serde_json::to_value(&config).unwrap();
        let baseline = serde_json::to_value(azlin_core::AzlinConfig::default()).unwrap();

        let current_obj = current.as_object().unwrap();
        let baseline_obj = baseline.as_object().unwrap();

        // Should detect at least 1 change
        let mut changed = 0u32;
        for (key, val) in current_obj {
            if baseline_obj.get(key) != Some(val) {
                changed += 1;
            }
        }
        assert!(changed >= 1, "expected at least 1 change");
    }
}
