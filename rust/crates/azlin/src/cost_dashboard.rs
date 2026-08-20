//! Ratatui-based cost dashboard TUI with budget tracking charts.

use crossterm::{
    event::{self, Event, KeyCode},
    terminal::{disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen},
    ExecutableCommand,
};
use ratatui::{
    backend::CrosstermBackend,
    layout::{Constraint, Direction, Layout, Rect},
    style::{Color, Modifier, Style},
    text::Line,
    widgets::{Bar, BarChart, BarGroup, Block, Borders, Cell, Gauge, Row, Table},
    Terminal,
};
use std::io::IsTerminal;

#[derive(Debug, Clone)]
pub struct DailyCost {
    pub date: String,
    pub amount: f64,
}

#[derive(Debug, Clone)]
pub struct VmCost {
    pub name: String,
    pub cost: f64,
}

#[derive(Debug, Clone)]
pub struct BudgetInfo {
    pub limit: f64,
    pub current_spend: f64,
    pub currency: String,
}

impl BudgetInfo {
    pub fn usage_pct(&self) -> f64 {
        if self.limit <= 0.0 {
            0.0
        } else {
            (self.current_spend / self.limit * 100.0).min(100.0)
        }
    }
    pub fn alert_color(&self) -> Color {
        let p = self.usage_pct();
        if p >= 90.0 {
            Color::Red
        } else if p >= 70.0 {
            Color::Yellow
        } else {
            Color::Green
        }
    }
}

/// What the dashboard shows when it has no total to show.
pub const UNAVAILABLE_TOTAL: &str = "unavailable";

#[derive(Debug, Clone)]
pub struct CostDashboardData {
    pub resource_group: String,
    /// `None` when the usage query failed. `Some(vec![])` means the query
    /// succeeded and the period genuinely cost nothing. Collapsing the two
    /// into an empty vector is what let a failed fetch render as `$-0.00`:
    /// Rust sums an empty `f64` iterator from `-0.0`, so the dashboard even
    /// printed a *negative* zero total and still exited 0.
    pub daily_costs: Option<Vec<DailyCost>>,
    pub vm_costs: Option<Vec<VmCost>>,
    pub budget: Option<BudgetInfo>,
    pub period_label: String,
    /// Sources that could not be fetched, each with the reason, so the
    /// dashboard can say what is missing instead of implying it is zero.
    pub unavailable: Vec<String>,
}

impl CostDashboardData {
    /// The period total, or `None` when there is no usage data behind it.
    ///
    /// The `== 0.0` branch normalises negative zero. Rust's `Sum` for `f64`
    /// folds from `-0.0`, so a period with no rows totals `-0.0` and formats
    /// as `$-0.00` — a figure no cost report can legitimately produce, and
    /// the tell that gave the original bug away.
    pub fn total_spend(&self) -> Option<f64> {
        self.daily_costs.as_ref().map(|days| {
            let total: f64 = days.iter().map(|d| d.amount).sum();
            if total == 0.0 {
                0.0
            } else {
                total
            }
        })
    }

    /// The total formatted for display, or the word "unavailable".
    pub fn total_spend_label(&self) -> String {
        match self.total_spend() {
            Some(t) => format!("${:.2}", t),
            None => UNAVAILABLE_TOTAL.to_string(),
        }
    }

    /// Daily costs, empty when the query failed. Callers that need to tell
    /// "failed" from "cost nothing" read `daily_costs` directly.
    pub fn daily(&self) -> &[DailyCost] {
        self.daily_costs.as_deref().unwrap_or_default()
    }

    pub fn trend_arrow(&self) -> &'static str {
        let daily = match self.daily_costs.as_ref() {
            // No data is not a flat trend. `→` next to a missing total read
            // as "spending is steady" when nothing had been measured.
            None => return "?",
            Some(d) => d,
        };
        if daily.len() < 2 {
            return "\u{2192}";
        }
        let mid = daily.len() / 2;
        let earlier: f64 = daily[..mid].iter().map(|d| d.amount).sum();
        let recent: f64 = daily[mid..].iter().map(|d| d.amount).sum();
        if recent > earlier * 1.1 {
            "\u{2191}"
        } else if recent < earlier * 0.9 {
            "\u{2193}"
        } else {
            "\u{2192}"
        }
    }

    pub fn top_vms(&self, n: usize) -> Vec<&VmCost> {
        let mut sorted: Vec<&VmCost> = self
            .vm_costs
            .as_deref()
            .unwrap_or_default()
            .iter()
            .collect();
        sorted.sort_by(|a, b| {
            b.cost
                .partial_cmp(&a.cost)
                .unwrap_or(std::cmp::Ordering::Equal)
        });
        sorted.truncate(n);
        sorted
    }

    /// True when no source produced anything — the case where the dashboard
    /// has nothing to say and the caller should fail rather than print zeros.
    pub fn is_empty_of_data(&self) -> bool {
        self.daily_costs.is_none() && self.vm_costs.is_none() && self.budget.is_none()
    }
}

pub fn run_cost_dashboard(data: &CostDashboardData) -> anyhow::Result<()> {
    if !std::io::stdout().is_terminal() {
        print_plain_dashboard(data);
        return Ok(());
    }
    enable_raw_mode()?;
    std::io::stdout().execute(EnterAlternateScreen)?;
    let backend = CrosstermBackend::new(std::io::stdout());
    let mut terminal = Terminal::new(backend)?;
    let result = run_tui_loop(&mut terminal, data);
    disable_raw_mode()?;
    std::io::stdout().execute(LeaveAlternateScreen)?;
    result
}

fn run_tui_loop(
    terminal: &mut Terminal<CrosstermBackend<std::io::Stdout>>,
    data: &CostDashboardData,
) -> anyhow::Result<()> {
    loop {
        terminal.draw(|f| render_dashboard(f, data))?;
        if event::poll(std::time::Duration::from_secs(30))? {
            if let Event::Key(key) = event::read()? {
                if matches!(key.code, KeyCode::Char('q') | KeyCode::Esc) {
                    break;
                }
            }
        }
    }
    Ok(())
}

fn render_dashboard(f: &mut ratatui::Frame, data: &CostDashboardData) {
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(3),
            Constraint::Min(10),
            Constraint::Length(3),
        ])
        .split(f.area());
    render_header(f, chunks[0], data);
    render_main(f, chunks[1], data);
    let footer = Block::default()
        .title(" q: quit ")
        .borders(Borders::ALL)
        .border_style(Style::default().fg(Color::DarkGray));
    f.render_widget(footer, chunks[2]);
}

fn render_header(f: &mut ratatui::Frame, area: Rect, data: &CostDashboardData) {
    let title = format!(
        " Cost Dashboard: {} | Total: {} {} | {} ",
        data.resource_group,
        data.total_spend_label(),
        data.budget
            .as_ref()
            .map(|b| b.currency.as_str())
            .unwrap_or("USD"),
        data.trend_arrow()
    );
    let header = Block::default()
        .title(title)
        .borders(Borders::ALL)
        .border_style(Style::default().fg(Color::Cyan));
    f.render_widget(header, area);
}

fn render_main(f: &mut ratatui::Frame, area: Rect, data: &CostDashboardData) {
    let chunks = Layout::default()
        .direction(Direction::Horizontal)
        .constraints([Constraint::Percentage(60), Constraint::Percentage(40)])
        .split(area);
    render_bar_chart(f, chunks[0], data);
    let right = Layout::default()
        .direction(Direction::Vertical)
        .constraints([Constraint::Length(5), Constraint::Min(5)])
        .split(chunks[1]);
    render_budget_gauge(f, right[0], data);
    render_top_vms(f, right[1], data);
}

fn render_bar_chart(f: &mut ratatui::Frame, area: Rect, data: &CostDashboardData) {
    let max = data.daily().iter().map(|d| d.amount).fold(0.0f64, f64::max);
    let bars: Vec<Bar> = data
        .daily()
        .iter()
        .map(|d| {
            let label = if d.date.len() >= 5 {
                d.date[5..].to_string()
            } else {
                d.date.clone()
            };
            let color = if max > 0.0 && d.amount / max > 0.8 {
                Color::Red
            } else if max > 0.0 && d.amount / max > 0.5 {
                Color::Yellow
            } else {
                Color::Green
            };
            Bar::default()
                .value((d.amount * 100.0) as u64)
                .label(Line::from(label))
                .style(Style::default().fg(color))
        })
        .collect();
    let chart = BarChart::default()
        .block(
            Block::default()
                .title(format!(" Daily Spend ({}) ", data.period_label))
                .borders(Borders::ALL),
        )
        .data(BarGroup::default().bars(&bars))
        .bar_width(5)
        .bar_gap(1)
        .direction(Direction::Vertical);
    f.render_widget(chart, area);
}

fn render_budget_gauge(f: &mut ratatui::Frame, area: Rect, data: &CostDashboardData) {
    if let Some(ref budget) = data.budget {
        let pct = budget.usage_pct();
        let color = budget.alert_color();
        let label = format!(
            "${:.2} / ${:.2} ({:.0}%)",
            budget.current_spend, budget.limit, pct
        );
        let gauge = Gauge::default()
            .block(
                Block::default()
                    .title(" Budget ")
                    .borders(Borders::ALL)
                    .border_style(Style::default().fg(color)),
            )
            .gauge_style(Style::default().fg(color).add_modifier(Modifier::BOLD))
            .ratio(pct / 100.0)
            .label(label);
        f.render_widget(gauge, area);
    } else {
        f.render_widget(
            Block::default()
                .title(" Budget: Not configured ")
                .borders(Borders::ALL)
                .border_style(Style::default().fg(Color::DarkGray)),
            area,
        );
    }
}

fn render_top_vms(f: &mut ratatui::Frame, area: Rect, data: &CostDashboardData) {
    let top = data.top_vms(5);
    let header = Row::new(vec![
        Cell::from("VM").style(Style::default().fg(Color::Yellow)),
        Cell::from("Cost").style(Style::default().fg(Color::Yellow)),
    ]);
    let rows: Vec<Row> = top
        .iter()
        .map(|vm| {
            Row::new(vec![
                Cell::from(vm.name.as_str()),
                Cell::from(format!("${:.2}", vm.cost)),
            ])
        })
        .collect();
    let table = Table::new(
        rows,
        [Constraint::Percentage(60), Constraint::Percentage(40)],
    )
    .header(header)
    .block(
        Block::default()
            .title(" Top 5 Expensive VMs ")
            .borders(Borders::ALL),
    );
    f.render_widget(table, area);
}

pub fn print_plain_dashboard(data: &CostDashboardData) {
    print!("{}", format_plain_dashboard(data));
}

/// Render the non-TTY dashboard as text.
///
/// Split out from the printer so the "what is missing" reporting can be
/// asserted: the whole point of this rendering is that an unavailable source
/// is named rather than left as an empty section the reader takes for zero.
pub fn format_plain_dashboard(data: &CostDashboardData) -> String {
    use std::fmt::Write;
    let mut out = String::new();
    let _ = writeln!(out, "Cost Dashboard for '{}'", data.resource_group);
    let _ = writeln!(
        out,
        "Period: {} | Trend: {} | Total: {}",
        data.period_label,
        data.trend_arrow(),
        data.total_spend_label()
    );
    // Name every source that failed. Without this the reader sees empty
    // sections and reads them as "nothing was spent".
    for reason in &data.unavailable {
        let _ = writeln!(out, "!! {}", reason);
    }
    if let Some(ref b) = data.budget {
        let p = b.usage_pct();
        let s = if p >= 90.0 {
            "CRITICAL"
        } else if p >= 70.0 {
            "WARNING"
        } else {
            "OK"
        };
        let _ = writeln!(
            out,
            "Budget: ${:.2} / ${:.2} ({:.0}%) [{}]",
            b.current_spend, b.limit, p, s
        );
    }
    let _ = writeln!(out, "\nDaily costs:");
    match data.daily_costs.as_ref() {
        None => {
            let _ = writeln!(out, "  ({})", UNAVAILABLE_TOTAL);
        }
        Some(days) if days.is_empty() => {
            let _ = writeln!(out, "  (no usage recorded in this period)");
        }
        Some(days) => {
            for d in days {
                let _ = writeln!(out, "  {} ${:>8.2}", d.date, d.amount);
            }
        }
    }
    let _ = writeln!(out, "\nTop 5 expensive VMs:");
    match data.vm_costs.as_ref() {
        None => {
            let _ = writeln!(out, "  ({})", UNAVAILABLE_TOTAL);
        }
        Some(vms) if vms.is_empty() => {
            let _ = writeln!(out, "  (no per-VM usage recorded in this period)");
        }
        Some(_) => {
            for vm in data.top_vms(5) {
                let _ = writeln!(out, "  {:<20} ${:.2}", vm.name, vm.cost);
            }
        }
    }
    out
}

pub fn parse_daily_costs(entries: &[serde_json::Value]) -> Vec<DailyCost> {
    let mut m: std::collections::BTreeMap<String, f64> = std::collections::BTreeMap::new();
    for e in entries {
        let d = e
            .get("usageStart")
            .and_then(|v| v.as_str())
            .and_then(|s| s.get(..10))
            .unwrap_or("unknown");
        let c = e.get("pretaxCost").and_then(|v| v.as_f64()).unwrap_or(0.0);
        *m.entry(d.to_string()).or_insert(0.0) += c;
    }
    m.into_iter()
        .map(|(date, amount)| DailyCost { date, amount })
        .collect()
}

pub fn parse_vm_costs(entries: &[serde_json::Value]) -> Vec<VmCost> {
    let mut m: std::collections::HashMap<String, f64> = std::collections::HashMap::new();
    for e in entries {
        let inst = e
            .get("instanceName")
            .and_then(|v| v.as_str())
            .unwrap_or("unknown");
        let name = inst.rsplit('/').next().unwrap_or(inst);
        let c = e.get("pretaxCost").and_then(|v| v.as_f64()).unwrap_or(0.0);
        *m.entry(name.to_string()).or_insert(0.0) += c;
    }
    let mut r: Vec<VmCost> = m
        .into_iter()
        .map(|(name, cost)| VmCost { name, cost })
        .collect();
    r.sort_by(|a, b| {
        b.cost
            .partial_cmp(&a.cost)
            .unwrap_or(std::cmp::Ordering::Equal)
    });
    r
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sample_data() -> CostDashboardData {
        CostDashboardData {
            resource_group: "rg".into(),
            period_label: "7d".into(),
            daily_costs: Some(vec![
                DailyCost {
                    date: "2025-01-01".into(),
                    amount: 10.0,
                },
                DailyCost {
                    date: "2025-01-02".into(),
                    amount: 15.0,
                },
                DailyCost {
                    date: "2025-01-03".into(),
                    amount: 12.0,
                },
                DailyCost {
                    date: "2025-01-04".into(),
                    amount: 20.0,
                },
            ]),
            vm_costs: Some(vec![
                VmCost {
                    name: "vm-1".into(),
                    cost: 25.0,
                },
                VmCost {
                    name: "vm-2".into(),
                    cost: 15.0,
                },
                VmCost {
                    name: "vm-3".into(),
                    cost: 10.0,
                },
            ]),
            budget: Some(BudgetInfo {
                limit: 100.0,
                current_spend: 57.0,
                currency: "USD".into(),
            }),
            unavailable: Vec::new(),
        }
    }

    #[test]
    fn test_total_spend() {
        assert!((sample_data().total_spend().unwrap() - 57.0).abs() < 0.01);
    }

    /// A failed fetch has no total. Rust sums an empty `f64` iterator from
    /// `-0.0`, so the old code did not merely print zero — it printed
    /// `Total: $-0.00`, a figure no cost report can legitimately produce,
    /// and exited 0.
    #[test]
    fn a_failed_fetch_has_no_total_rather_than_a_zero_one() {
        let d = CostDashboardData {
            daily_costs: None,
            vm_costs: None,
            unavailable: vec!["Usage data unavailable: RBACAccessDenied".into()],
            ..sample_data()
        };
        assert_eq!(d.total_spend(), None);
        assert_eq!(d.total_spend_label(), UNAVAILABLE_TOTAL);
        assert!(
            !d.total_spend_label().contains('0'),
            "{}",
            d.total_spend_label()
        );
    }

    /// A period that genuinely cost nothing is a different fact from one
    /// that could not be measured, and both have to be expressible.
    #[test]
    fn a_genuinely_empty_period_still_has_a_total_of_zero() {
        let d = CostDashboardData {
            daily_costs: Some(Vec::new()),
            vm_costs: Some(Vec::new()),
            budget: None,
            ..sample_data()
        };
        assert_eq!(d.total_spend(), Some(0.0));
        assert_eq!(d.total_spend_label(), "$0.00");
    }

    /// No data is not a flat trend. `→` beside a missing total read as
    /// "spending is steady" when nothing had been measured at all.
    #[test]
    fn missing_data_is_not_a_flat_trend() {
        let d = CostDashboardData {
            daily_costs: None,
            ..sample_data()
        };
        assert_eq!(d.trend_arrow(), "?");
    }

    /// An empty section reads as "nothing was spent". The reason it is
    /// empty has to appear in the same output.
    #[test]
    fn the_plain_dashboard_names_what_it_could_not_fetch() {
        let d = CostDashboardData {
            daily_costs: None,
            vm_costs: None,
            budget: None,
            unavailable: vec!["Usage data unavailable: RBACAccessDenied".into()],
            ..sample_data()
        };
        let text = format_plain_dashboard(&d);
        assert!(text.contains("RBACAccessDenied"), "{text}");
        assert!(text.contains(UNAVAILABLE_TOTAL), "{text}");
        assert!(!text.contains("$-0.00"), "{text}");
        assert!(!text.contains("$0.00"), "{text}");
    }

    /// A period that really cost nothing says so in words, so it is not
    /// confused with the failure case above.
    #[test]
    fn the_plain_dashboard_distinguishes_zero_from_unknown() {
        let d = CostDashboardData {
            daily_costs: Some(Vec::new()),
            vm_costs: Some(Vec::new()),
            budget: None,
            unavailable: Vec::new(),
            ..sample_data()
        };
        let text = format_plain_dashboard(&d);
        assert!(text.contains("$0.00"), "{text}");
        assert!(text.contains("no usage recorded"), "{text}");
        assert!(!text.contains(UNAVAILABLE_TOTAL), "{text}");
    }

    /// The caller uses this to decide whether to fail instead of drawing an
    /// empty dashboard.
    #[test]
    fn every_source_failing_is_detectable() {
        let d = CostDashboardData {
            daily_costs: None,
            vm_costs: None,
            budget: None,
            ..sample_data()
        };
        assert!(d.is_empty_of_data());
        assert!(!sample_data().is_empty_of_data());
    }
    #[test]
    fn test_trend_arrow_up() {
        let d = CostDashboardData {
            daily_costs: Some(vec![
                DailyCost {
                    date: "1".into(),
                    amount: 5.0,
                },
                DailyCost {
                    date: "2".into(),
                    amount: 5.0,
                },
                DailyCost {
                    date: "3".into(),
                    amount: 15.0,
                },
                DailyCost {
                    date: "4".into(),
                    amount: 15.0,
                },
            ]),
            ..sample_data()
        };
        assert_eq!(d.trend_arrow(), "\u{2191}");
    }
    #[test]
    fn test_trend_arrow_down() {
        let d = CostDashboardData {
            daily_costs: Some(vec![
                DailyCost {
                    date: "1".into(),
                    amount: 20.0,
                },
                DailyCost {
                    date: "2".into(),
                    amount: 20.0,
                },
                DailyCost {
                    date: "3".into(),
                    amount: 5.0,
                },
                DailyCost {
                    date: "4".into(),
                    amount: 5.0,
                },
            ]),
            ..sample_data()
        };
        assert_eq!(d.trend_arrow(), "\u{2193}");
    }
    #[test]
    fn test_top_vms() {
        let d = sample_data();
        let t = d.top_vms(2);
        assert_eq!(t.len(), 2);
        assert_eq!(t[0].name, "vm-1");
    }
    #[test]
    fn test_budget_pct() {
        assert!(
            (BudgetInfo {
                limit: 100.0,
                current_spend: 75.0,
                currency: "USD".into()
            }
            .usage_pct()
                - 75.0)
                .abs()
                < 0.01
        );
    }
    #[test]
    fn test_budget_alert_green() {
        assert_eq!(
            BudgetInfo {
                limit: 100.0,
                current_spend: 50.0,
                currency: "USD".into()
            }
            .alert_color(),
            Color::Green
        );
    }
    #[test]
    fn test_budget_alert_yellow() {
        assert_eq!(
            BudgetInfo {
                limit: 100.0,
                current_spend: 75.0,
                currency: "USD".into()
            }
            .alert_color(),
            Color::Yellow
        );
    }
    #[test]
    fn test_budget_alert_red() {
        assert_eq!(
            BudgetInfo {
                limit: 100.0,
                current_spend: 95.0,
                currency: "USD".into()
            }
            .alert_color(),
            Color::Red
        );
    }
    #[test]
    fn test_parse_daily_costs() {
        let e = vec![
            serde_json::json!({"usageStart": "2025-01-01T00:00:00", "pretaxCost": 10.0}),
            serde_json::json!({"usageStart": "2025-01-01T12:00:00", "pretaxCost": 5.0}),
        ];
        let d = parse_daily_costs(&e);
        assert_eq!(d.len(), 1);
        assert!((d[0].amount - 15.0).abs() < 0.01);
    }
    #[test]
    fn test_parse_vm_costs() {
        let e = vec![
            serde_json::json!({"instanceName": "/sub/rg/vm/dev-1", "pretaxCost": 10.0}),
            serde_json::json!({"instanceName": "dev-2", "pretaxCost": 8.0}),
        ];
        let c = parse_vm_costs(&e);
        assert_eq!(c.len(), 2);
        assert_eq!(c[0].name, "dev-1");
    }
}
