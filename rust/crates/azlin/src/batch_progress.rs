//! Multi-progress bar support for batch VM operations (start, stop, restart).
//!
//! Each VM gets its own spinner showing real-time status. A summary line at the
//! bottom tracks overall progress. Falls back to plain text when stdout is not
//! a TTY.

use std::io::IsTerminal;
use std::time::Instant;

use indicatif::{MultiProgress, ProgressBar, ProgressStyle};

/// Status of a single VM operation.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum VmOpStatus {
    Pending,
    InProgress,
    Success,
    Failed(String),
}

/// Result of a single VM operation within a batch.
#[derive(Debug, Clone)]
pub struct VmOpResult {
    pub vm_id: String,
    pub vm_name: String,
    pub status: VmOpStatus,
    pub elapsed: std::time::Duration,
}

/// Summary of a completed batch operation.
#[derive(Debug)]
pub struct BatchSummary {
    pub results: Vec<VmOpResult>,
    pub total_elapsed: std::time::Duration,
}

impl BatchSummary {
    pub fn succeeded(&self) -> usize {
        self.results.iter().filter(|r| r.status == VmOpStatus::Success).count()
    }

    pub fn failed(&self) -> usize {
        self.results.iter().filter(|r| matches!(r.status, VmOpStatus::Failed(_))).count()
    }

    /// Format a final summary string with color-coded results.
    pub fn format_summary(&self, action: &str) -> String {
        let mut out = String::new();
        out.push_str(&format!(
            "\nBatch {} complete: {} succeeded, {} failed ({:.1}s)\n",
            action, self.succeeded(), self.failed(), self.total_elapsed.as_secs_f64()
        ));
        for r in &self.results {
            let (icon, color) = match &r.status {
                VmOpStatus::Success => ("\x1b[32m\u{2713}\x1b[0m", "\x1b[32m"),
                VmOpStatus::Failed(_) => ("\x1b[31m\u{2717}\x1b[0m", "\x1b[31m"),
                _ => (" ", ""),
            };
            let status_text = match &r.status {
                VmOpStatus::Success => "success".to_string(),
                VmOpStatus::Failed(msg) => format!("failed: {}", msg),
                VmOpStatus::Pending => "pending".to_string(),
                VmOpStatus::InProgress => "in-progress".to_string(),
            };
            out.push_str(&format!(
                "  {} {}{:>20}\x1b[0m  {} ({:.1}s)\n",
                icon, color, r.vm_name, status_text, r.elapsed.as_secs_f64()
            ));
        }
        out
    }
}

/// Penguin spinner frames for batch progress.
const PENGUIN_TICKS: &[&str] = &[
    "\u{1f427}\u{00b7}\u{00b7}\u{00b7}\u{00b7}\u{00b7}",
    "\u{00b7}\u{1f427}\u{00b7}\u{00b7}\u{00b7}\u{00b7}",
    "\u{00b7}\u{00b7}\u{1f427}\u{00b7}\u{00b7}\u{00b7}",
    "\u{00b7}\u{00b7}\u{00b7}\u{1f427}\u{00b7}\u{00b7}",
    "\u{00b7}\u{00b7}\u{00b7}\u{00b7}\u{1f427}\u{00b7}",
    "\u{00b7}\u{00b7}\u{00b7}\u{00b7}\u{00b7}\u{1f427}",
    "\u{00b7}\u{00b7}\u{00b7}\u{00b7}\u{1f427}\u{00b7}",
    "\u{00b7}\u{00b7}\u{00b7}\u{1f427}\u{00b7}\u{00b7}",
    "\u{00b7}\u{00b7}\u{1f427}\u{00b7}\u{00b7}\u{00b7}",
    "\u{00b7}\u{1f427}\u{00b7}\u{00b7}\u{00b7}\u{00b7}",
];

fn batch_spinner_style() -> ProgressStyle {
    ProgressStyle::default_spinner()
        .tick_strings(PENGUIN_TICKS)
        .template("{prefix:.bold} {spinner} {msg}")
        .expect("valid spinner template")
}

/// Execute a batch operation on multiple VMs with per-VM progress bars.
pub fn run_batch_with_progress(
    action: &str,
    vm_ids: &[&str],
    vm_names: &std::collections::HashMap<String, String>,
) -> BatchSummary {
    let is_tty = std::io::stdout().is_terminal();
    let start = Instant::now();

    if !is_tty {
        return run_batch_plain(action, vm_ids, vm_names, start);
    }

    let mp = MultiProgress::new();
    let style = batch_spinner_style();

    let bars: Vec<(ProgressBar, &str)> = vm_ids
        .iter()
        .map(|id| {
            let name = resolve_vm_name(id, vm_names);
            let pb = mp.add(ProgressBar::new_spinner());
            pb.set_style(style.clone());
            pb.set_prefix(format!("{:>20}", name));
            pb.set_message("\x1b[34mpending\x1b[0m");
            pb.enable_steady_tick(std::time::Duration::from_millis(120));
            (pb, *id)
        })
        .collect();

    let summary_pb = mp.add(ProgressBar::new(vm_ids.len() as u64));
    summary_pb.set_style(
        ProgressStyle::default_bar()
            .template("  {bar:30.cyan/dim} {pos}/{len} VMs completed")
            .expect("valid bar template"),
    );

    let mut results = Vec::with_capacity(vm_ids.len());
    for (pb, id) in &bars {
        let name = resolve_vm_name(id, vm_names);
        let op_start = Instant::now();
        pb.set_message(format!("\x1b[36m{}\x1b[0m", action));

        let output = std::process::Command::new("az")
            .args(["vm", action, "--ids", id, "--no-wait"])
            .output();

        let elapsed = op_start.elapsed();
        let status = match output {
            Ok(o) if o.status.success() => {
                pb.finish_with_message(format!("\x1b[32msuccess\x1b[0m ({:.1}s)", elapsed.as_secs_f64()));
                VmOpStatus::Success
            }
            Ok(o) => {
                let err = String::from_utf8_lossy(&o.stderr).lines().next().unwrap_or("unknown error").to_string();
                pb.finish_with_message(format!("\x1b[31mfailed\x1b[0m ({:.1}s)", elapsed.as_secs_f64()));
                VmOpStatus::Failed(err)
            }
            Err(e) => {
                pb.finish_with_message(format!("\x1b[31merror\x1b[0m ({:.1}s)", elapsed.as_secs_f64()));
                VmOpStatus::Failed(e.to_string())
            }
        };

        summary_pb.inc(1);
        results.push(VmOpResult { vm_id: id.to_string(), vm_name: name.to_string(), status, elapsed });
    }

    summary_pb.finish_and_clear();
    BatchSummary { results, total_elapsed: start.elapsed() }
}

fn run_batch_plain(action: &str, vm_ids: &[&str], vm_names: &std::collections::HashMap<String, String>, start: Instant) -> BatchSummary {
    let mut results = Vec::with_capacity(vm_ids.len());
    for (i, id) in vm_ids.iter().enumerate() {
        let name = resolve_vm_name(id, vm_names);
        let op_start = Instant::now();
        eprintln!("[{}/{}] {} {}...", i + 1, vm_ids.len(), action, name);
        let output = std::process::Command::new("az").args(["vm", action, "--ids", id, "--no-wait"]).output();
        let elapsed = op_start.elapsed();
        let status = match output {
            Ok(o) if o.status.success() => { eprintln!("  -> success ({:.1}s)", elapsed.as_secs_f64()); VmOpStatus::Success }
            Ok(o) => { let err = String::from_utf8_lossy(&o.stderr).lines().next().unwrap_or("unknown error").to_string(); eprintln!("  -> failed: {} ({:.1}s)", err, elapsed.as_secs_f64()); VmOpStatus::Failed(err) }
            Err(e) => { eprintln!("  -> error: {} ({:.1}s)", e, elapsed.as_secs_f64()); VmOpStatus::Failed(e.to_string()) }
        };
        results.push(VmOpResult { vm_id: id.to_string(), vm_name: name.to_string(), status, elapsed });
    }
    BatchSummary { results, total_elapsed: start.elapsed() }
}

fn resolve_vm_name<'a>(id: &'a str, names: &'a std::collections::HashMap<String, String>) -> &'a str {
    if let Some(name) = names.get(id) { name.as_str() } else { id.rsplit('/').next().unwrap_or(id) }
}

pub fn parse_vm_id_name_pairs(tsv: &str) -> std::collections::HashMap<String, String> {
    let mut map = std::collections::HashMap::new();
    for line in tsv.lines() {
        let parts: Vec<&str> = line.split('\t').collect();
        if parts.len() >= 2 { map.insert(parts[0].to_string(), parts[1].to_string()); }
    }
    map
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_resolve_vm_name_from_map() {
        let mut names = std::collections::HashMap::new();
        names.insert("/sub/rg/vm/myvm".to_string(), "my-vm".to_string());
        assert_eq!(resolve_vm_name("/sub/rg/vm/myvm", &names), "my-vm");
    }

    #[test]
    fn test_resolve_vm_name_from_resource_id() {
        let names = std::collections::HashMap::new();
        assert_eq!(resolve_vm_name("/subscriptions/x/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/dev-vm-1", &names), "dev-vm-1");
    }

    #[test]
    fn test_parse_vm_id_name_pairs() {
        let tsv = "/sub/rg/vm/vm1\tvm1\n/sub/rg/vm/vm2\tvm2\n";
        let pairs = parse_vm_id_name_pairs(tsv);
        assert_eq!(pairs.len(), 2);
        assert_eq!(pairs.get("/sub/rg/vm/vm1").unwrap(), "vm1");
    }

    #[test]
    fn test_parse_vm_id_name_pairs_empty() {
        assert!(parse_vm_id_name_pairs("").is_empty());
    }

    #[test]
    fn test_batch_summary_counts() {
        let summary = BatchSummary {
            results: vec![
                VmOpResult { vm_id: "id1".into(), vm_name: "vm1".into(), status: VmOpStatus::Success, elapsed: std::time::Duration::from_secs(1) },
                VmOpResult { vm_id: "id2".into(), vm_name: "vm2".into(), status: VmOpStatus::Failed("err".into()), elapsed: std::time::Duration::from_secs(2) },
                VmOpResult { vm_id: "id3".into(), vm_name: "vm3".into(), status: VmOpStatus::Success, elapsed: std::time::Duration::from_secs(1) },
            ],
            total_elapsed: std::time::Duration::from_secs(4),
        };
        assert_eq!(summary.succeeded(), 2);
        assert_eq!(summary.failed(), 1);
    }

    #[test]
    fn test_batch_summary_format() {
        let summary = BatchSummary {
            results: vec![
                VmOpResult { vm_id: "id1".into(), vm_name: "vm1".into(), status: VmOpStatus::Success, elapsed: std::time::Duration::from_millis(500) },
                VmOpResult { vm_id: "id2".into(), vm_name: "vm2".into(), status: VmOpStatus::Failed("timeout".into()), elapsed: std::time::Duration::from_millis(3000) },
            ],
            total_elapsed: std::time::Duration::from_millis(3500),
        };
        let text = summary.format_summary("stop");
        assert!(text.contains("1 succeeded"));
        assert!(text.contains("1 failed"));
        assert!(text.contains("vm1"));
        assert!(text.contains("timeout"));
    }
}
