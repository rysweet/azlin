/// Resolve the compose file path, defaulting to "docker-compose.yml".
#[allow(dead_code)]
pub fn resolve_compose_file(file: Option<&str>) -> String {
    file.unwrap_or("docker-compose.yml").to_string()
}

/// Build a docker compose command string for a given subcommand and file.
pub fn build_compose_cmd(subcommand: &str, file: &str) -> String {
    format!("docker compose -f {} {}", file, subcommand)
}
