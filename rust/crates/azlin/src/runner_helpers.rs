/// Generate a runner VM name from pool name and index.
pub fn build_runner_vm_name(pool: &str, index: usize) -> String {
    format!("azlin-runner-{}-{}", pool, index + 1)
}

/// Build the tag string for a runner VM.
pub fn build_runner_tags(pool: &str, repo: &str) -> String {
    format!("azlin-runner=true pool={} repo={}", pool, repo)
}

/// Build a runner pool TOML config as a map of key-value pairs.
pub fn build_runner_config(
    pool: &str,
    repo: &str,
    count: u32,
    labels: &str,
    rg: &str,
    vm_size: &str,
    timestamp: &str,
) -> Vec<(String, toml::Value)> {
    vec![
        ("pool".to_string(), toml::Value::String(pool.to_string())),
        ("repo".to_string(), toml::Value::String(repo.to_string())),
        ("count".to_string(), toml::Value::Integer(count as i64)),
        (
            "labels".to_string(),
            toml::Value::String(labels.to_string()),
        ),
        (
            "resource_group".to_string(),
            toml::Value::String(rg.to_string()),
        ),
        (
            "vm_size".to_string(),
            toml::Value::String(vm_size.to_string()),
        ),
        ("enabled".to_string(), toml::Value::Boolean(true)),
        (
            "created".to_string(),
            toml::Value::String(timestamp.to_string()),
        ),
    ]
}

/// Build the pool config file name.
pub fn pool_config_filename(pool: &str) -> String {
    format!("{}.toml", pool)
}
