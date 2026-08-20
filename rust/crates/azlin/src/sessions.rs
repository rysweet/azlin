use super::*;

use std::path::Path;

/// Build a session TOML value.
pub fn build_session_toml(
    name: &str,
    resource_group: &str,
    vms: &[String],
    description: Option<&str>,
) -> toml::Value {
    let mut session = toml::map::Map::new();
    session.insert("name".to_string(), toml::Value::String(name.to_string()));
    session.insert(
        "resource_group".to_string(),
        toml::Value::String(resource_group.to_string()),
    );
    let vm_array: Vec<toml::Value> = vms.iter().map(|v| toml::Value::String(v.clone())).collect();
    session.insert("vms".to_string(), toml::Value::Array(vm_array));
    // `--description` was accepted and discarded, so the one field that tells a
    // future reader what a saved session was *for* never reached the file
    // (#1089). Blank is treated as absent: a `description = ""` in the TOML
    // reads as "someone set it to nothing" rather than "nobody set it".
    if let Some(text) = description.map(str::trim).filter(|d| !d.is_empty()) {
        session.insert(
            "description".to_string(),
            toml::Value::String(text.to_string()),
        );
    }
    session.insert(
        "created".to_string(),
        toml::Value::String(chrono::Utc::now().to_rfc3339()),
    );
    toml::Value::Table(session)
}

/// The description a saved session carries, if any.
pub fn session_description(content: &str) -> Option<String> {
    content
        .parse::<toml::Value>()
        .ok()?
        .as_table()?
        .get("description")?
        .as_str()
        .map(str::to_string)
}

/// Parse a session TOML and return (resource_group, vms, created).
pub fn parse_session_toml(content: &str) -> Result<(String, Vec<String>, String), anyhow::Error> {
    let session: toml::Value = content.parse()?;
    let default_tbl = toml::map::Map::new();
    let tbl = session.as_table().unwrap_or(&default_tbl);
    let rg = tbl
        .get("resource_group")
        .and_then(|v| v.as_str())
        .unwrap_or("-")
        .to_string();
    let vms = tbl
        .get("vms")
        .and_then(|v| v.as_array())
        .map(|arr| {
            arr.iter()
                .filter_map(|v| v.as_str().map(String::from))
                .collect()
        })
        .unwrap_or_default();
    let created = tbl
        .get("created")
        .and_then(|v| v.as_str())
        .unwrap_or("-")
        .to_string();
    Ok((rg, vms, created))
}

/// List session names from a directory.
pub fn list_session_names(dir: &Path) -> Result<Vec<String>, anyhow::Error> {
    if !dir.exists() {
        return Ok(Vec::new());
    }
    let mut names = Vec::new();
    for entry in std::fs::read_dir(dir)? {
        let entry = entry?;
        let fname = entry.file_name().to_string_lossy().to_string();
        if fname.ends_with(".toml") {
            names.push(fname.trim_end_matches(".toml").to_string());
        }
    }
    Ok(names)
}
