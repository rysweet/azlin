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
        self.results
            .iter()
            .filter(|r| r.status == VmOpStatus::Success)
            .count()
    }

    pub fn failed(&self) -> usize {
        self.results
            .iter()
            .filter(|r| matches!(r.status, VmOpStatus::Failed(_)))
            .count()
    }

    /// Format a final summary string with color-coded results.
    pub fn format_summary(&self, action: &str) -> String {
        let mut out = String::new();
        out.push_str(&format!(
            "\nBatch {} complete: {} succeeded, {} failed ({:.1}s)\n",
            action,
            self.succeeded(),
            self.failed(),
            self.total_elapsed.as_secs_f64()
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
                icon,
                color,
                r.vm_name,
                status_text,
                r.elapsed.as_secs_f64()
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

/// Sustained ARM write rate a batch is allowed to reach, in operations per
/// second, and the burst it may open with.
///
/// `az vm stop --no-wait` returns immediately, so `--max-workers 50` would put
/// fifty ARM writes in flight and keep them coming. The sequential loop this
/// replaced was accidentally a rate limiter; removing it is the point of the
/// flag, and something has to take its place or the first large batch finds
/// out what Azure Resource Manager thinks about it — as a wall of 429s that
/// look like azlin's fault.
///
/// These numbers are deliberately conservative: ARM's write limits are
/// per-subscription and shared with everything else the user is running, and a
/// batch that finishes in twelve seconds instead of eight is not the problem
/// this flag was raised to solve.
const ARM_WRITES_PER_SECOND: f64 = 10.0;
const ARM_WRITE_BURST: f64 = 10.0;

/// Run one `az vm <action> --ids <id> --no-wait` and classify the outcome.
///
/// Pulled out of both drivers so the parallel path cannot drift from the
/// sequential one in how it decides success.
///
/// `limiter` paces the ARM write; with one worker it never blocks.
fn run_one_vm_op(
    action: &str,
    id: &str,
    limiter: &azlin_azure::rate_limiter::RateLimiter,
) -> (VmOpStatus, std::time::Duration) {
    limiter.acquire();
    let op_start = Instant::now();
    let output = std::process::Command::new("az")
        .args(["vm", action, "--ids", id, "--no-wait"])
        .output();
    let elapsed = op_start.elapsed();
    let status = match output {
        Ok(o) if o.status.success() => VmOpStatus::Success,
        Ok(o) => VmOpStatus::Failed(
            String::from_utf8_lossy(&o.stderr)
                .lines()
                .next()
                .unwrap_or("unknown error")
                .to_string(),
        ),
        Err(e) => VmOpStatus::Failed(e.to_string()),
    };
    (status, elapsed)
}

/// Run `f` over every index, at most `workers` at a time, filling `slots`.
///
/// Results stay in input order whatever order the operations finish in, so
/// `--max-workers` changes how long a batch takes and never what it reports.
/// One worker keeps the in-line loop rather than spawning a thread to do
/// nothing but wait.
pub(crate) fn for_each_bounded<F>(count: usize, workers: usize, f: F)
where
    F: Fn(usize) + Sync,
{
    if workers <= 1 || count <= 1 {
        (0..count).for_each(f);
        return;
    }
    let next = std::sync::atomic::AtomicUsize::new(0);
    let f = &f;
    let next_ref = &next;
    std::thread::scope(|scope| {
        for _ in 0..workers.min(count) {
            scope.spawn(move || loop {
                let i = next_ref.fetch_add(1, std::sync::atomic::Ordering::SeqCst);
                if i >= count {
                    break;
                }
                f(i);
            });
        }
    });
}

/// Execute a batch operation on multiple VMs with per-VM progress bars.
///
/// `workers` is `--max-workers`. Each VM costs a full `az` process start even
/// with `--no-wait`, so a sequential run over fifty VMs spent a minute and a
/// half in Python startup while the flag that was meant to fix that was
/// discarded (#1089).
pub fn run_batch_with_progress(
    action: &str,
    vm_ids: &[&str],
    vm_names: &std::collections::HashMap<String, String>,
    workers: usize,
) -> BatchSummary {
    let is_tty = std::io::stdout().is_terminal();
    let start = Instant::now();

    if !is_tty {
        return run_batch_plain(action, vm_ids, vm_names, workers, start);
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

    let limiter =
        azlin_azure::rate_limiter::RateLimiter::new(ARM_WRITE_BURST, ARM_WRITES_PER_SECOND);
    let slots: Vec<std::sync::Mutex<Option<VmOpResult>>> = (0..vm_ids.len())
        .map(|_| std::sync::Mutex::new(None))
        .collect();
    for_each_bounded(vm_ids.len(), workers, |i| {
        let (pb, id) = &bars[i];
        let name = resolve_vm_name(id, vm_names);
        pb.set_message(format!("\x1b[36m{}\x1b[0m", action));
        let (status, elapsed) = run_one_vm_op(action, id, &limiter);
        let label = match &status {
            VmOpStatus::Success => "\x1b[32msuccess\x1b[0m",
            VmOpStatus::Failed(_) => "\x1b[31mfailed\x1b[0m",
            _ => "\x1b[31merror\x1b[0m",
        };
        pb.finish_with_message(format!("{} ({:.1}s)", label, elapsed.as_secs_f64()));
        summary_pb.inc(1);
        *slots[i].lock().expect("batch result slot poisoned") = Some(VmOpResult {
            vm_id: id.to_string(),
            vm_name: name.to_string(),
            status,
            elapsed,
        });
    });

    summary_pb.finish_and_clear();
    BatchSummary {
        results: slots
            .into_iter()
            .map(|slot| {
                slot.into_inner()
                    .expect("batch result slot poisoned")
                    .expect("every batch slot is filled before the scope ends")
            })
            .collect(),
        total_elapsed: start.elapsed(),
    }
}

fn run_batch_plain(
    action: &str,
    vm_ids: &[&str],
    vm_names: &std::collections::HashMap<String, String>,
    workers: usize,
    start: Instant,
) -> BatchSummary {
    let limiter =
        azlin_azure::rate_limiter::RateLimiter::new(ARM_WRITE_BURST, ARM_WRITES_PER_SECOND);
    let slots: Vec<std::sync::Mutex<Option<VmOpResult>>> = (0..vm_ids.len())
        .map(|_| std::sync::Mutex::new(None))
        .collect();
    let done = std::sync::atomic::AtomicUsize::new(0);
    for_each_bounded(vm_ids.len(), workers, |i| {
        let id = vm_ids[i];
        let name = resolve_vm_name(id, vm_names);
        let (status, elapsed) = run_one_vm_op(action, id, &limiter);
        // Numbered on completion rather than on start: with several workers in
        // flight, "[3/50] starting" printed before "[1/50] done" reads as an
        // ordering that never happened.
        let n = done.fetch_add(1, std::sync::atomic::Ordering::SeqCst) + 1;
        match &status {
            VmOpStatus::Success => eprintln!(
                "[{}/{}] {} {} -> success ({:.1}s)",
                n,
                vm_ids.len(),
                action,
                name,
                elapsed.as_secs_f64()
            ),
            VmOpStatus::Failed(err) => eprintln!(
                "[{}/{}] {} {} -> failed: {} ({:.1}s)",
                n,
                vm_ids.len(),
                action,
                name,
                err,
                elapsed.as_secs_f64()
            ),
            _ => {}
        }
        *slots[i].lock().expect("batch result slot poisoned") = Some(VmOpResult {
            vm_id: id.to_string(),
            vm_name: name.to_string(),
            status,
            elapsed,
        });
    });
    BatchSummary {
        results: slots
            .into_iter()
            .map(|slot| {
                slot.into_inner()
                    .expect("batch result slot poisoned")
                    .expect("every batch slot is filled before the scope ends")
            })
            .collect(),
        total_elapsed: start.elapsed(),
    }
}

fn resolve_vm_name<'a>(
    id: &'a str,
    names: &'a std::collections::HashMap<String, String>,
) -> &'a str {
    if let Some(name) = names.get(id) {
        name.as_str()
    } else {
        id.rsplit('/').next().unwrap_or(id)
    }
}

pub fn parse_vm_id_name_pairs(tsv: &str) -> std::collections::HashMap<String, String> {
    let mut map = std::collections::HashMap::new();
    for line in tsv.lines() {
        let parts: Vec<&str> = line.split('\t').collect();
        if parts.len() >= 2 {
            map.insert(parts[0].to_string(), parts[1].to_string());
        }
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
                VmOpResult {
                    vm_id: "id1".into(),
                    vm_name: "vm1".into(),
                    status: VmOpStatus::Success,
                    elapsed: std::time::Duration::from_secs(1),
                },
                VmOpResult {
                    vm_id: "id2".into(),
                    vm_name: "vm2".into(),
                    status: VmOpStatus::Failed("err".into()),
                    elapsed: std::time::Duration::from_secs(2),
                },
                VmOpResult {
                    vm_id: "id3".into(),
                    vm_name: "vm3".into(),
                    status: VmOpStatus::Success,
                    elapsed: std::time::Duration::from_secs(1),
                },
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
                VmOpResult {
                    vm_id: "id1".into(),
                    vm_name: "vm1".into(),
                    status: VmOpStatus::Success,
                    elapsed: std::time::Duration::from_millis(500),
                },
                VmOpResult {
                    vm_id: "id2".into(),
                    vm_name: "vm2".into(),
                    status: VmOpStatus::Failed("timeout".into()),
                    elapsed: std::time::Duration::from_millis(3000),
                },
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
