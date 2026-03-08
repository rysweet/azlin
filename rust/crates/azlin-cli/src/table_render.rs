//! Reusable box-drawing table renderer with truncation (no comfy_table).
//!
//! Produces solid-border tables that truncate content with `…` instead of wrapping.
//! Adapts column widths proportionally when the terminal is too narrow.

/// Truncate string to exactly `w` visible characters, padding or adding `…`.
pub fn trunc(s: &str, w: usize) -> String {
    if w == 0 {
        return String::new();
    }
    let chars: Vec<char> = s.chars().collect();
    if chars.len() <= w {
        format!("{:<width$}", s, width = w)
    } else if w <= 1 {
        chars[..w].iter().collect()
    } else {
        let truncated: String = chars[..w - 1].iter().collect();
        format!("{}…", truncated)
    }
}

/// Right-aligned truncate to exactly `w` visible characters.
pub fn trunc_right(s: &str, w: usize) -> String {
    if w == 0 {
        return String::new();
    }
    let chars: Vec<char> = s.chars().collect();
    if chars.len() <= w {
        format!("{:>width$}", s, width = w)
    } else if w <= 1 {
        chars[..w].iter().collect()
    } else {
        let truncated: String = chars[..w - 1].iter().collect();
        format!("{}…", truncated)
    }
}

/// Draw a horizontal border line with box-drawing characters.
pub fn border_line(widths: &[usize], left: char, mid: char, right: char, fill: char) -> String {
    let mut line = String::new();
    line.push(left);
    for (i, w) in widths.iter().enumerate() {
        for _ in 0..*w + 2 {
            line.push(fill);
        }
        if i + 1 < widths.len() {
            line.push(mid);
        }
    }
    line.push(right);
    line
}

/// Render a single row with box-drawing vertical borders.
pub fn render_row(cells: &[String], widths: &[usize]) -> String {
    let mut line = String::from("│");
    for (i, (cell, _w)) in cells.iter().zip(widths.iter()).enumerate() {
        line.push(' ');
        line.push_str(cell);
        line.push(' ');
        if i + 1 < widths.len() {
            line.push('│');
        }
    }
    line.push('│');
    line
}

/// A simple box-drawing table that truncates content instead of wrapping.
pub struct SimpleTable {
    headers: Vec<String>,
    widths: Vec<usize>,
    right_align: Vec<bool>,
    rows: Vec<Vec<String>>,
}

impl SimpleTable {
    /// Create a new table with headers and column widths.
    pub fn new(headers: &[&str], widths: &[usize]) -> Self {
        let n = headers.len();
        Self {
            headers: headers.iter().map(|h| h.to_string()).collect(),
            widths: widths.to_vec(),
            right_align: vec![false; n],
            rows: Vec::new(),
        }
    }

    /// Mark a column as right-aligned.
    pub fn right_align(mut self, col: usize) -> Self {
        if col < self.right_align.len() {
            self.right_align[col] = true;
        }
        self
    }

    /// Add a row of cell strings.
    pub fn add_row(&mut self, cells: Vec<String>) {
        self.rows.push(cells);
    }

    /// Render the full table as a string with box-drawing borders.
    ///
    /// Shrinks columns proportionally if the table exceeds terminal width.
    pub fn render(&self) -> String {
        let term_width = crossterm::terminal::size()
            .map(|(w, _)| w as usize)
            .unwrap_or(120);

        let mut widths = self.widths.clone();

        // Shrink proportionally if total exceeds terminal
        let border_overhead = widths.len() * 3 + 1;
        let content_budget = term_width.saturating_sub(border_overhead);
        let total_content: usize = widths.iter().sum();
        if total_content > content_budget && total_content > 0 {
            let ratio = content_budget as f64 / total_content as f64;
            for w in &mut widths {
                *w = (*w as f64 * ratio).floor().max(3.0) as usize;
            }
        }

        let mut out = String::new();

        // Top border
        out.push_str(&border_line(&widths, '┌', '┬', '┐', '─'));
        out.push('\n');

        // Header row
        let header_cells: Vec<String> = self
            .headers
            .iter()
            .zip(widths.iter())
            .enumerate()
            .map(|(i, (h, &w))| {
                if self.right_align.get(i).copied().unwrap_or(false) {
                    trunc_right(h, w)
                } else {
                    trunc(h, w)
                }
            })
            .collect();
        out.push_str(&render_row(&header_cells, &widths));
        out.push('\n');

        // Header separator
        out.push_str(&border_line(&widths, '├', '┼', '┤', '─'));
        out.push('\n');

        // Data rows
        for row in &self.rows {
            let cells: Vec<String> = row
                .iter()
                .zip(widths.iter())
                .enumerate()
                .map(|(i, (cell, &w))| {
                    if self.right_align.get(i).copied().unwrap_or(false) {
                        trunc_right(cell, w)
                    } else {
                        trunc(cell, w)
                    }
                })
                .collect();
            out.push_str(&render_row(&cells, &widths));
            out.push('\n');
        }

        // Bottom border
        out.push_str(&border_line(&widths, '└', '┴', '┘', '─'));

        out
    }
}

impl std::fmt::Display for SimpleTable {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.render())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_trunc_pads_short_strings() {
        assert_eq!(trunc("hi", 5), "hi   ");
    }

    #[test]
    fn test_trunc_truncates_long_strings() {
        assert_eq!(trunc("hello world", 5), "hell…");
    }

    #[test]
    fn test_trunc_exact_fit() {
        assert_eq!(trunc("hello", 5), "hello");
    }

    #[test]
    fn test_trunc_zero_width() {
        assert_eq!(trunc("hello", 0), "");
    }

    #[test]
    fn test_simple_table_render() {
        let mut t = SimpleTable::new(&["Name", "Value"], &[10, 6]);
        t.add_row(vec!["foo".into(), "42".into()]);
        t.add_row(vec!["a-long-name-here".into(), "999999".into()]);
        let out = t.render();
        assert!(out.contains("Name"));
        assert!(out.contains("foo"));
        assert!(out.contains("┌"));
        assert!(out.contains("┘"));
        // Long name should be truncated
        assert!(out.contains("…"));
    }

    #[test]
    fn test_simple_table_right_align() {
        let t = SimpleTable::new(&["X"], &[5]).right_align(0);
        let out = t.render();
        assert!(out.contains("    X"));
    }

    #[test]
    fn test_simple_table_display() {
        let t = SimpleTable::new(&["A"], &[3]);
        let s = format!("{}", t);
        assert!(s.contains("A"));
    }
}
