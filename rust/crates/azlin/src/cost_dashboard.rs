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

#[derive(Debug, Clone)]
pub struct CostDashboardData {
    pub resource_group: String,
    pub daily_costs: Vec<DailyCost>,
    pub vm_costs: Vec<VmCost>,
    pub budget: Option<BudgetInfo>,
    pub period_label: String,
}

impl CostDashboardData {
    pub fn total_spend(&self) -> f64 {
        self.daily_costs.iter().map(|d| d.amount).sum()
    }

    pub fn trend_arrow(&self) -> &'static str {
        if self.daily_costs.len() < 2 {
            return "\u{2192}";
        }
        let mid = self.daily_costs.len() / 2;
        let earlier: f64 = self.daily_costs[..mid].iter().map(|d| d.amount).sum();
        let recent: f64 = self.daily_costs[mid..].iter().map(|d| d.amount).sum();
        if recent > earlier * 1.1 {
            "\u{2191}"
        } else if recent < earlier * 0.9 {
            "\u{2193}"
        } else {
            "\u{2192}"
        }
    }

    pub fn top_vms(&self, n: usize) -> Vec<&VmCost> {
        let mut sorted: Vec<&VmCost> = self.vm_costs.iter().collect();
        sorted.sort_by(|a, b| {
            b.cost
                .partial_cmp(&a.cost)
                .unwrap_or(std::cmp::Ordering::Equal)
        });
        sorted.truncate(n);
        sorted
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
        " Cost Dashboard: {} | Total: ${:.2} {} | {} ",
        data.resource_group,
        data.total_spend(),
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
    let max = data
        .daily_costs
        .iter()
        .map(|d| d.amount)
        .fold(0.0f64, f64::max);
    let bars: Vec<Bar> = data
        .daily_costs
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
    println!("Cost Dashboard for '{}'", data.resource_group);
    println!(
        "Period: {} | Trend: {} | Total: ${:.2}",
        data.period_label,
        data.trend_arrow(),
        data.total_spend()
    );
    if let Some(ref b) = data.budget {
        let p = b.usage_pct();
        let s = if p >= 90.0 {
            "CRITICAL"
        } else if p >= 70.0 {
            "WARNING"
        } else {
            "OK"
        };
        println!(
            "Budget: ${:.2} / ${:.2} ({:.0}%) [{}]",
            b.current_spend, b.limit, p, s
        );
    }
    println!("\nDaily costs:");
    for d in &data.daily_costs {
        println!("  {} ${:>8.2}", d.date, d.amount);
    }
    println!("\nTop 5 expensive VMs:");
    for vm in data.top_vms(5) {
        println!("  {:<20} ${:.2}", vm.name, vm.cost);
    }
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
            daily_costs: vec![
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
            ],
            vm_costs: vec![
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
            ],
            budget: Some(BudgetInfo {
                limit: 100.0,
                current_spend: 57.0,
                currency: "USD".into(),
            }),
        }
    }

    #[test]
    fn test_total_spend() {
        assert!((sample_data().total_spend() - 57.0).abs() < 0.01);
    }
    #[test]
    fn test_trend_arrow_up() {
        let d = CostDashboardData {
            daily_costs: vec![
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
            ],
            ..sample_data()
        };
        assert_eq!(d.trend_arrow(), "\u{2191}");
    }
    #[test]
    fn test_trend_arrow_down() {
        let d = CostDashboardData {
            daily_costs: vec![
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
            ],
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
