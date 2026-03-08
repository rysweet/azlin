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

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    #[test]
    fn test_build_context_toml_minimal() {
        let toml_str = build_context_toml("test", None, None, None, None, None).unwrap();
        assert!(toml_str.contains("name = \"test\""));
    }

    #[test]
    fn test_build_context_toml_full() {
        let toml_str = build_context_toml(
            "prod",
            Some("sub-123"),
            Some("tenant-456"),
            Some("rg-prod"),
            Some("westus2"),
            Some("my-kv"),
        )
        .unwrap();
        assert!(toml_str.contains("name = \"prod\""));
        assert!(toml_str.contains("subscription_id = \"sub-123\""));
        assert!(toml_str.contains("tenant_id = \"tenant-456\""));
        assert!(toml_str.contains("resource_group = \"rg-prod\""));
        assert!(toml_str.contains("region = \"westus2\""));
        assert!(toml_str.contains("key_vault_name = \"my-kv\""));
    }

    #[test]
    fn test_list_contexts_empty_dir() {
        let tmp = TempDir::new().unwrap();
        let contexts = list_contexts(tmp.path(), "default").unwrap();
        assert!(contexts.is_empty());
    }

    #[test]
    fn test_list_contexts_with_files() {
        let tmp = TempDir::new().unwrap();
        std::fs::write(tmp.path().join("default.toml"), "name = \"default\"").unwrap();
        std::fs::write(tmp.path().join("staging.toml"), "name = \"staging\"").unwrap();
        std::fs::write(tmp.path().join("README.md"), "not a context").unwrap();

        let contexts = list_contexts(tmp.path(), "default").unwrap();
        assert_eq!(contexts.len(), 2);

        // One should be active
        let active_count = contexts.iter().filter(|(_, is_active)| *is_active).count();
        assert_eq!(active_count, 1);

        let default_entry = contexts.iter().find(|(n, _)| n == "default").unwrap();
        assert!(default_entry.1); // is_active
    }

    #[test]
    fn test_rename_context_file() {
        let tmp = TempDir::new().unwrap();
        let content = "name = \"old-ctx\"\nresource_group = \"rg1\"\n";
        std::fs::write(tmp.path().join("old-ctx.toml"), content).unwrap();

        rename_context_file(tmp.path(), "old-ctx", "new-ctx").unwrap();

        assert!(!tmp.path().join("old-ctx.toml").exists());
        assert!(tmp.path().join("new-ctx.toml").exists());

        let new_content = std::fs::read_to_string(tmp.path().join("new-ctx.toml")).unwrap();
        assert!(new_content.contains("\"new-ctx\""));
    }

    #[test]
    fn test_rename_context_file_not_found() {
        let tmp = TempDir::new().unwrap();
        let err = rename_context_file(tmp.path(), "nonexistent", "new").unwrap_err();
        assert!(err.to_string().contains("not found"));
    }

    #[test]
    fn test_read_context_resource_group() {
        let tmp = TempDir::new().unwrap();
        let path = tmp.path().join("ctx.toml");
        std::fs::write(&path, "name = \"my-ctx\"\nresource_group = \"my-rg\"\n").unwrap();

        let (name, rg) = read_context_resource_group(&path).unwrap();
        assert_eq!(name, "my-ctx");
        assert_eq!(rg, Some("my-rg".to_string()));
    }

    #[test]
    fn test_read_context_resource_group_no_rg() {
        let tmp = TempDir::new().unwrap();
        let path = tmp.path().join("ctx.toml");
        std::fs::write(&path, "name = \"my-ctx\"\n").unwrap();

        let (name, rg) = read_context_resource_group(&path).unwrap();
        assert_eq!(name, "my-ctx");
        assert_eq!(rg, None);
    }
}
