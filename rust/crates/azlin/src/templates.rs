use super::*;

use std::path::{Path, PathBuf};

/// Build template TOML content from fields.
pub fn build_template_toml(
    name: &str,
    description: Option<&str>,
    vm_size: Option<&str>,
    region: Option<&str>,
    cloud_init: Option<&str>,
) -> toml::Value {
    let mut tbl = toml::map::Map::new();
    tbl.insert("name".into(), toml::Value::String(name.to_string()));
    tbl.insert(
        "description".into(),
        toml::Value::String(description.unwrap_or("").to_string()),
    );
    tbl.insert(
        "vm_size".into(),
        toml::Value::String(vm_size.unwrap_or("Standard_D4s_v3").to_string()),
    );
    tbl.insert(
        "region".into(),
        toml::Value::String(region.unwrap_or("westus2").to_string()),
    );
    if let Some(ci) = cloud_init {
        tbl.insert("cloud_init".into(), toml::Value::String(ci.to_string()));
    }
    toml::Value::Table(tbl)
}

/// Save a template TOML value to the given directory.
pub fn save_template(dir: &Path, name: &str, tpl: &toml::Value) -> Result<PathBuf, anyhow::Error> {
    super::name_validation::validate_name(name)
        .map_err(|e| anyhow::anyhow!("Invalid template name: {}", e))?;
    std::fs::create_dir_all(dir)?;
    let path = dir.join(format!("{}.toml", name));
    std::fs::write(
        &path,
        toml::to_string_pretty(tpl)
            .map_err(|e| anyhow::anyhow!("TOML serialization error: {e}"))?,
    )?;
    Ok(path)
}

/// Load a template TOML from the given directory.
pub fn load_template(dir: &Path, name: &str) -> Result<toml::Value, anyhow::Error> {
    super::name_validation::validate_name(name)
        .map_err(|e| anyhow::anyhow!("Invalid template name: {}", e))?;
    let path = dir.join(format!("{}.toml", name));
    if !path.exists() {
        anyhow::bail!("Template '{}' not found.", name);
    }
    let content = std::fs::read_to_string(&path)?;
    Ok(content.parse()?)
}

/// List templates in the directory. Returns Vec of (name, vm_size, region).
pub fn list_templates(dir: &Path) -> Result<Vec<Vec<String>>, anyhow::Error> {
    if !dir.exists() {
        return Ok(Vec::new());
    }
    let mut rows: Vec<Vec<String>> = Vec::new();
    for entry in std::fs::read_dir(dir)? {
        let entry = entry?;
        let fname = entry.file_name().to_string_lossy().to_string();
        if fname.ends_with(".toml") {
            let content = std::fs::read_to_string(entry.path())?;
            let tpl: toml::Value = content
                .parse()
                .unwrap_or(toml::Value::Table(Default::default()));
            rows.push(vec![
                tpl.get("name")
                    .and_then(|v| v.as_str())
                    .unwrap_or("-")
                    .to_string(),
                tpl.get("vm_size")
                    .and_then(|v| v.as_str())
                    .unwrap_or("-")
                    .to_string(),
                tpl.get("region")
                    .and_then(|v| v.as_str())
                    .unwrap_or("-")
                    .to_string(),
            ]);
        }
    }
    Ok(rows)
}

/// Delete a template by name. Returns error if not found.
pub fn delete_template(dir: &Path, name: &str) -> Result<(), anyhow::Error> {
    super::name_validation::validate_name(name)
        .map_err(|e| anyhow::anyhow!("Invalid template name: {}", e))?;
    let path = dir.join(format!("{}.toml", name));
    if !path.exists() {
        anyhow::bail!("Template '{}' not found.", name);
    }
    std::fs::remove_file(&path)?;
    Ok(())
}

/// Import a template from a file, returning the template name.
pub fn import_template(dir: &Path, content: &str) -> Result<String, anyhow::Error> {
    let tpl: toml::Value = content.parse()?;
    let name = tpl
        .get("name")
        .and_then(|v| v.as_str())
        .ok_or_else(|| anyhow::anyhow!("Template missing 'name' field"))?
        .to_string();
    // validate_name is called inside save_template
    save_template(dir, &name, &tpl)?;
    Ok(name)
}
