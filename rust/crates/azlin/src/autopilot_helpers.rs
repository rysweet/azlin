/// Build the autopilot TOML config as a toml::Value::Table.
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

/// Build the budget name for a resource group.
pub fn build_budget_name(resource_group: &str) -> String {
    format!("azlin-budget-{}", resource_group)
}

/// Build the killall VM filter query for `az vm list`.
pub fn build_prefix_filter_query(prefix: &str) -> String {
    format!("[?starts_with(name, '{}')].id", prefix)
}

/// Build the cost management scope string.
pub fn build_cost_scope(subscription_id: &str, resource_group: &str) -> String {
    format!(
        "/subscriptions/{}/resourceGroups/{}",
        subscription_id, resource_group
    )
}
