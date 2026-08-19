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

    /// The file `build_context_toml` writes must round-trip through the
    /// reader that commands actually use. These were two parsers before
    /// #1090 — a resource-group-only reader here, and nothing at all for the
    /// subscription — and only one of them was ever consulted.
    #[test]
    fn built_context_round_trips_through_the_reader() {
        let toml_str = build_context_toml(
            "prod",
            Some("sub-prod"),
            Some("tenant-1"),
            Some("prod-rg"),
            Some("westus2"),
            None,
        )
        .unwrap();

        let ctx = crate::active_context::parse_context("prod", &toml_str).unwrap();
        assert_eq!(ctx.name, "prod");
        assert_eq!(ctx.subscription_id.as_deref(), Some("sub-prod"));
        assert_eq!(ctx.tenant_id.as_deref(), Some("tenant-1"));
        assert_eq!(ctx.resource_group.as_deref(), Some("prod-rg"));
        assert_eq!(ctx.region.as_deref(), Some("westus2"));
    }

    #[test]
    fn renamed_context_round_trips_through_the_reader() {
        let tmp = TempDir::new().unwrap();
        std::fs::write(
            tmp.path().join("old.toml"),
            "name = \"old\"\nsubscription_id = \"sub-1\"\nresource_group = \"rg-1\"\n",
        )
        .unwrap();

        rename_context_file(tmp.path(), "old", "new").unwrap();

        let content = std::fs::read_to_string(tmp.path().join("new.toml")).unwrap();
        let ctx = crate::active_context::parse_context("new", &content).unwrap();
        assert_eq!(ctx.name, "new");
        assert_eq!(ctx.subscription_id.as_deref(), Some("sub-1"));
        assert_eq!(ctx.resource_group.as_deref(), Some("rg-1"));
    }
}
