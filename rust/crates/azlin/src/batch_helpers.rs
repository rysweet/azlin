/// Parse VM resource IDs from the TSV output of
/// `az vm list -g <rg> --query "[].id" -o tsv`.
pub fn parse_vm_ids(tsv_output: &str) -> Vec<&str> {
    tsv_output.lines().filter(|l| !l.is_empty()).collect()
}

/// Build the `az` argument list for a batch VM operation.
/// `action` is e.g. `"deallocate"` or `"start"`.
pub fn build_batch_args<'a>(action: &'a str, ids: &[&'a str]) -> Vec<&'a str> {
    let mut args = vec!["vm", action, "--ids"];
    args.extend(ids);
    args
}

/// Build the JMESPath query for `az vm list`.
///
/// If `tag` is `Some("key=value")`, returns a filter like
/// `[?tags.KEY=='VALUE'].id`.  Otherwise returns `[].id`.
pub fn build_vm_list_query(tag: Option<&str>) -> Result<String, String> {
    match tag {
        Some(t) => {
            let (key, value) = super::tag_helpers::parse_tag(t)
                .ok_or_else(|| format!("Invalid tag format '{}'. Use key=value.", t))?;
            // Reject characters that could break JMESPath / shell quoting
            for ch in ['\'', '"', '\\', '`', '$', ';', '|', '&', '\n', '\r'] {
                if key.contains(ch) || value.contains(ch) {
                    return Err(format!(
                        "Tag key or value contains disallowed character '{}'",
                        ch.escape_default()
                    ));
                }
            }
            Ok(format!("[?tags.{}=='{}'].id", key, value))
        }
        None => Ok("[].id".to_string()),
    }
}

/// Summarise the result of a batch operation as a user-facing message.
pub fn summarise_batch(action: &str, rg: &str, success: bool) -> String {
    if success {
        format!("Batch {} completed for resource group '{}'", action, rg)
    } else {
        format!("Batch {} failed. Run commands individually.", action)
    }
}
