use super::*;

use std::path::Path;

/// Build a context TOML string from fields.
pub fn build_context_toml(
    name: &str,
    subscription_id: Option<&str>,
    tenant_id: Option<&str>,
    resource_group: Option<&str>,
    region: Option<&str>,
    key_vault_name: Option<&str>,
) -> Result<String, anyhow::Error> {
    let mut ctx = toml::map::Map::new();
    ctx.insert("name".to_string(), toml::Value::String(name.to_string()));
    if let Some(v) = subscription_id {
        ctx.insert(
            "subscription_id".to_string(),
            toml::Value::String(v.to_string()),
        );
    }
    if let Some(v) = tenant_id {
        ctx.insert("tenant_id".to_string(), toml::Value::String(v.to_string()));
    }
    if let Some(v) = resource_group {
        ctx.insert(
            "resource_group".to_string(),
            toml::Value::String(v.to_string()),
        );
    }
    if let Some(v) = region {
        ctx.insert("region".to_string(), toml::Value::String(v.to_string()));
    }
    if let Some(v) = key_vault_name {
        ctx.insert(
            "key_vault_name".to_string(),
            toml::Value::String(v.to_string()),
        );
    }
    Ok(toml::to_string_pretty(&toml::Value::Table(ctx))?)
}

/// List contexts in a directory. Returns Vec of (name, is_active).
pub fn list_contexts(ctx_dir: &Path, active: &str) -> Result<Vec<(String, bool)>, anyhow::Error> {
    let mut entries: Vec<_> = std::fs::read_dir(ctx_dir)?.filter_map(|e| e.ok()).collect();
    entries.sort_by_key(|e| e.file_name());
    let mut result = Vec::new();
    for entry in entries {
        let name = entry.file_name().to_string_lossy().to_string();
        if name.ends_with(".toml") {
            let ctx_name = name.trim_end_matches(".toml").to_string();
            let is_active = ctx_name == active;
            result.push((ctx_name, is_active));
        }
    }
    Ok(result)
}

/// Rename a context: update the name field in the TOML, rename the file,
/// and return whether the active context was renamed.
pub fn rename_context_file(
    ctx_dir: &Path,
    old_name: &str,
    new_name: &str,
) -> Result<(), anyhow::Error> {
    let old_path = ctx_dir.join(format!("{}.toml", old_name));
    let new_path = ctx_dir.join(format!("{}.toml", new_name));
    if !old_path.exists() {
        anyhow::bail!("Context '{}' not found.", old_name);
    }
    let content = std::fs::read_to_string(&old_path)?;
    let mut table: toml::Value = toml::from_str(&content)?;
    if let Some(t) = table.as_table_mut() {
        t.insert(
            "name".to_string(),
            toml::Value::String(new_name.to_string()),
        );
    }
    std::fs::write(&new_path, toml::to_string_pretty(&table)?)?;
    std::fs::remove_file(&old_path)?;
    Ok(())
}

/// Read a context TOML file and return (name, resource_group).
/// Returns `None` for resource_group when the field is absent.
pub fn read_context_resource_group(
    ctx_path: &Path,
) -> Result<(String, Option<String>), anyhow::Error> {
    let content = std::fs::read_to_string(ctx_path)?;
    let table: toml::Value = toml::from_str(&content)?;
    let name = table
        .get("name")
        .and_then(|v| v.as_str())
        .unwrap_or_else(|| {
            ctx_path
                .file_stem()
                .and_then(|s| s.to_str())
                .unwrap_or("unknown")
        })
        .to_string();
    let rg = table
        .get("resource_group")
        .and_then(|v| v.as_str())
        .map(|s| s.to_string());
    Ok((name, rg))
}
