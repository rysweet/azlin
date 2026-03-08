/// Render `rows` as CSV text with a header line.
pub fn format_as_csv(headers: &[&str], rows: &[Vec<String>]) -> String {
    let mut out = headers.join(",");
    for row in rows {
        out.push('\n');
        out.push_str(&row.join(","));
    }
    out
}

/// Render `rows` as a simple aligned-column table.
pub fn format_as_table(headers: &[&str], rows: &[Vec<String>]) -> String {
    let ncols = headers.len();
    let mut widths: Vec<usize> = headers.iter().map(|h| h.len()).collect();
    for row in rows {
        for (i, cell) in row.iter().enumerate() {
            if i < ncols && cell.len() > widths[i] {
                widths[i] = cell.len();
            }
        }
    }
    let mut out = String::new();
    for (i, h) in headers.iter().enumerate() {
        if i > 0 {
            out.push_str("  ");
        }
        out.push_str(&format!("{:<width$}", h, width = widths[i]));
    }
    for row in rows {
        out.push('\n');
        for (i, cell) in row.iter().enumerate() {
            if i > 0 {
                out.push_str("  ");
            }
            let w = if i < ncols { widths[i] } else { cell.len() };
            out.push_str(&format!("{:<width$}", cell, width = w));
        }
    }
    out
}

/// Serialize a slice to pretty-printed JSON. Returns an error string on failure.
pub fn format_as_json<T: serde::Serialize>(items: &[T]) -> String {
    serde_json::to_string_pretty(items).unwrap_or_else(|e| format!("JSON error: {e}"))
}
