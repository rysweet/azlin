//! Interactive TUI dashboard for VM fleet health monitoring.
//!
//! Provides a live-updating dashboard with:
//! - VM fleet table with selection and navigation
//! - Sparkline widgets for CPU/memory trends over time
//! - One-key actions: connect, start, stop VMs
//! - Vim-style keybindings (j/k/g/G) plus arrow keys

use std::collections::VecDeque;
use std::io;
use std::time::{Duration, Instant};

use anyhow::Result;
use crossterm::{
    event::{self, Event, KeyCode, KeyModifiers},
    terminal::{disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen},
    ExecutableCommand,
};
use ratatui::{
    backend::CrosstermBackend,
    layout::{Constraint, Direction, Layout, Rect},
    style::{Color, Modifier, Style},
    text::{Line, Span},
    widgets::{Block, Borders, Cell, Paragraph, Row, Sparkline, Table, TableState, Wrap},
    Frame, Terminal,
};

/// Maximum number of historical data points kept per VM for sparklines.
const HISTORY_CAPACITY: usize = 60;

/// A single VM's health snapshot with historical trend data.
pub struct VmDashboardEntry {
    pub vm_name: String,
    pub power_state: String,
    pub agent_status: String,
    pub error_count: u32,
    pub cpu_percent: f32,
    pub mem_percent: f32,
    pub disk_percent: f32,
    pub ip: String,
    pub region: String,
    pub sessions: u32,
    /// Rolling CPU history for sparkline (0..100 scaled to u64).
    pub cpu_history: VecDeque<u64>,
    /// Rolling memory history for sparkline (0..100 scaled to u64).
    pub mem_history: VecDeque<u64>,
}

impl VmDashboardEntry {
    pub fn new(vm_name: String) -> Self {
        Self {
            vm_name,
            power_state: String::new(),
            agent_status: String::new(),
            error_count: 0,
            cpu_percent: 0.0,
            mem_percent: 0.0,
            disk_percent: 0.0,
            ip: String::new(),
            region: String::new(),
            sessions: 0,
            cpu_history: VecDeque::with_capacity(HISTORY_CAPACITY),
            mem_history: VecDeque::with_capacity(HISTORY_CAPACITY),
        }
    }

    /// Push a new sample, evicting the oldest if at capacity.
    pub fn push_sample(&mut self, cpu: f32, mem: f32) {
        if self.cpu_history.len() >= HISTORY_CAPACITY {
            self.cpu_history.pop_front();
        }
        if self.mem_history.len() >= HISTORY_CAPACITY {
            self.mem_history.pop_front();
        }
        self.cpu_history.push_back(cpu.clamp(0.0, 100.0) as u64);
        self.mem_history.push_back(mem.clamp(0.0, 100.0) as u64);
    }
}

/// Pending action to execute on a VM after exiting the render loop.
pub enum VmAction {
    Connect(String),
    Start(String),
    Stop(String),
}

/// Application state for the TUI dashboard.
pub struct DashboardApp {
    pub entries: Vec<VmDashboardEntry>,
    pub table_state: TableState,
    pub status_message: String,
    pub pending_action: Option<VmAction>,
    pub should_quit: bool,
    pub last_refresh: Instant,
    pub refresh_interval: Duration,
    /// Count of completed refresh cycles (displayed in header).
    pub refresh_count: u32,
}

impl DashboardApp {
    pub fn new(interval_secs: u32) -> Self {
        let mut table_state = TableState::default();
        table_state.select(Some(0));
        Self {
            entries: Vec::new(),
            table_state,
            status_message: String::new(),
            pending_action: None,
            should_quit: false,
            last_refresh: Instant::now(),
            refresh_interval: Duration::from_secs(interval_secs as u64),
            refresh_count: 0,
        }
    }

    /// Index of the currently selected VM, if any.
    pub fn selected_index(&self) -> Option<usize> {
        self.table_state.selected()
    }

    /// Name of the currently selected VM, if any.
    pub fn selected_vm_name(&self) -> Option<&str> {
        self.selected_index()
            .and_then(|i| self.entries.get(i))
            .map(|e| e.vm_name.as_str())
    }

    /// Move selection down by one row.
    pub fn next(&mut self) {
        if self.entries.is_empty() {
            return;
        }
        let i = match self.table_state.selected() {
            Some(i) => {
                if i >= self.entries.len() - 1 {
                    0
                } else {
                    i + 1
                }
            }
            None => 0,
        };
        self.table_state.select(Some(i));
    }

    /// Move selection up by one row.
    pub fn previous(&mut self) {
        if self.entries.is_empty() {
            return;
        }
        let i = match self.table_state.selected() {
            Some(i) => {
                if i == 0 {
                    self.entries.len() - 1
                } else {
                    i - 1
                }
            }
            None => 0,
        };
        self.table_state.select(Some(i));
    }

    /// Jump to the first row.
    pub fn first(&mut self) {
        if !self.entries.is_empty() {
            self.table_state.select(Some(0));
        }
    }

    /// Jump to the last row.
    pub fn last(&mut self) {
        if !self.entries.is_empty() {
            self.table_state.select(Some(self.entries.len() - 1));
        }
    }

    /// Handle a keyboard event, returning true if the event was consumed.
    pub fn handle_key(&mut self, code: KeyCode, modifiers: KeyModifiers) -> bool {
        match code {
            KeyCode::Char('q') | KeyCode::Esc => {
                self.should_quit = true;
                true
            }
            KeyCode::Char('c') if modifiers.contains(KeyModifiers::CONTROL) => {
                self.should_quit = true;
                true
            }
            KeyCode::Char('j') | KeyCode::Down => {
                self.next();
                true
            }
            KeyCode::Char('k') | KeyCode::Up => {
                self.previous();
                true
            }
            KeyCode::Char('g') => {
                self.first();
                true
            }
            KeyCode::Char('G') => {
                self.last();
                true
            }
            KeyCode::Enter => {
                if let Some(name) = self.selected_vm_name().map(|s| s.to_string()) {
                    self.pending_action = Some(VmAction::Connect(name.clone()));
                    self.status_message = format!("Connecting to {}...", name);
                }
                true
            }
            KeyCode::Char('s') => {
                if let Some(name) = self.selected_vm_name().map(|s| s.to_string()) {
                    self.pending_action = Some(VmAction::Start(name.clone()));
                    self.status_message = format!("Starting {}...", name);
                }
                true
            }
            KeyCode::Char('x') => {
                if let Some(name) = self.selected_vm_name().map(|s| s.to_string()) {
                    self.pending_action = Some(VmAction::Stop(name.clone()));
                    self.status_message = format!("Stopping {}...", name);
                }
                true
            }
            KeyCode::Char('r') => {
                self.status_message = "Refreshing...".to_string();
                // Reset timer so next poll triggers immediate refresh
                self.last_refresh = Instant::now() - self.refresh_interval;
                true
            }
            _ => false,
        }
    }

    /// Whether enough time has elapsed for a data refresh.
    pub fn needs_refresh(&self) -> bool {
        self.last_refresh.elapsed() >= self.refresh_interval
    }

    /// Mark that a refresh just completed.
    pub fn mark_refreshed(&mut self) {
        self.last_refresh = Instant::now();
        self.refresh_count += 1;
    }
}

// ── Rendering ────────────────────────────────────────────────────────────

/// Color for a utilisation metric (green/yellow/red thresholds at 50/80).
fn metric_color(pct: f32) -> Color {
    if pct > 80.0 {
        Color::Red
    } else if pct > 50.0 {
        Color::Yellow
    } else {
        Color::Green
    }
}

/// Color for a VM power state.
fn state_color(state: &str) -> Color {
    match state {
        "Running" | "running" => Color::Green,
        "stopped" | "deallocated" | "Stopped" | "Deallocated" => Color::Red,
        _ => Color::Yellow,
    }
}

/// Color for agent status.
fn agent_color(status: &str) -> Color {
    match status {
        "OK" => Color::Green,
        "Down" => Color::Red,
        _ => Color::Yellow,
    }
}

/// Render the full dashboard frame.
pub fn render_dashboard(f: &mut Frame, app: &mut DashboardApp) {
    let chunks = Layout::default()
        .direction(Direction::Vertical)
        .constraints([
            Constraint::Length(3), // Header
            Constraint::Min(8),    // VM table
            Constraint::Length(8), // Sparklines panel
            Constraint::Length(3), // Footer / status
        ])
        .split(f.area());

    render_header(f, chunks[0], app);
    render_vm_table(f, chunks[1], app);
    render_sparklines(f, chunks[2], app);
    render_footer(f, chunks[3], app);
}

fn render_header(f: &mut Frame, area: Rect, app: &DashboardApp) {
    let now = chrono::Local::now().format("%H:%M:%S");
    let title = format!(
        " azlin fleet dashboard | {} | refresh #{} every {}s ",
        now,
        app.refresh_count,
        app.refresh_interval.as_secs()
    );
    let header = Block::default()
        .title(title)
        .borders(Borders::ALL)
        .border_style(Style::default().fg(Color::Cyan));
    f.render_widget(header, area);
}

fn render_vm_table(f: &mut Frame, area: Rect, app: &mut DashboardApp) {
    let header_cells = [
        "VM Name", "State", "Region", "IP", "Agent", "Errors", "CPU %", "Mem %", "Disk %",
        "Sessions",
    ]
    .iter()
    .map(|h| {
        Cell::from(*h).style(
            Style::default()
                .fg(Color::Yellow)
                .add_modifier(Modifier::BOLD),
        )
    });
    let header = Row::new(header_cells).height(1);

    let rows: Vec<Row> = app
        .entries
        .iter()
        .map(|e| {
            let cells = vec![
                Cell::from(e.vm_name.as_str()),
                Cell::from(e.power_state.as_str())
                    .style(Style::default().fg(state_color(&e.power_state))),
                Cell::from(e.region.as_str()),
                Cell::from(e.ip.as_str()),
                Cell::from(e.agent_status.as_str())
                    .style(Style::default().fg(agent_color(&e.agent_status))),
                Cell::from(format!("{}", e.error_count)).style(Style::default().fg(
                    if e.error_count > 10 {
                        Color::Red
                    } else if e.error_count > 0 {
                        Color::Yellow
                    } else {
                        Color::Green
                    },
                )),
                Cell::from(format!("{:.1}", e.cpu_percent))
                    .style(Style::default().fg(metric_color(e.cpu_percent))),
                Cell::from(format!("{:.1}", e.mem_percent))
                    .style(Style::default().fg(metric_color(e.mem_percent))),
                Cell::from(format!("{:.1}", e.disk_percent))
                    .style(Style::default().fg(metric_color(e.disk_percent))),
                Cell::from(format!("{}", e.sessions)),
            ];
            Row::new(cells)
        })
        .collect();

    let table = Table::new(
        rows,
        [
            Constraint::Percentage(16), // VM Name
            Constraint::Percentage(10), // State
            Constraint::Percentage(10), // Region
            Constraint::Percentage(14), // IP
            Constraint::Percentage(8),  // Agent
            Constraint::Percentage(7),  // Errors
            Constraint::Percentage(8),  // CPU
            Constraint::Percentage(8),  // Mem
            Constraint::Percentage(8),  // Disk
            Constraint::Percentage(8),  // Sessions
        ],
    )
    .header(header)
    .block(
        Block::default()
            .title(" Fleet Status ")
            .borders(Borders::ALL),
    )
    .row_highlight_style(
        Style::default()
            .bg(Color::DarkGray)
            .add_modifier(Modifier::BOLD),
    )
    .highlight_symbol(">> ");

    f.render_stateful_widget(table, area, &mut app.table_state);
}

fn render_sparklines(f: &mut Frame, area: Rect, app: &DashboardApp) {
    let selected = app.selected_index().and_then(|i| app.entries.get(i));

    let block = Block::default()
        .title(format!(
            " Trends: {} ",
            selected.map_or("(none selected)", |e| e.vm_name.as_str())
        ))
        .borders(Borders::ALL);

    let inner = block.inner(area);
    f.render_widget(block, area);

    if let Some(entry) = selected {
        let spark_chunks = Layout::default()
            .direction(Direction::Horizontal)
            .constraints([Constraint::Percentage(50), Constraint::Percentage(50)])
            .split(inner);

        // CPU sparkline
        let cpu_data: Vec<u64> = entry.cpu_history.iter().copied().collect();
        let cpu_label = format!("CPU {:.1}%", entry.cpu_percent);
        let cpu_sparkline = Sparkline::default()
            .block(Block::default().title(cpu_label))
            .data(&cpu_data)
            .max(100)
            .style(Style::default().fg(metric_color(entry.cpu_percent)));
        f.render_widget(cpu_sparkline, spark_chunks[0]);

        // Memory sparkline
        let mem_data: Vec<u64> = entry.mem_history.iter().copied().collect();
        let mem_label = format!("Mem {:.1}%", entry.mem_percent);
        let mem_sparkline = Sparkline::default()
            .block(Block::default().title(mem_label))
            .data(&mem_data)
            .max(100)
            .style(Style::default().fg(metric_color(entry.mem_percent)));
        f.render_widget(mem_sparkline, spark_chunks[1]);
    }
}

fn render_footer(f: &mut Frame, area: Rect, app: &DashboardApp) {
    let keys = vec![
        Span::styled("q", Style::default().fg(Color::Yellow)),
        Span::raw(":quit "),
        Span::styled("j/k", Style::default().fg(Color::Yellow)),
        Span::raw(":nav "),
        Span::styled("Enter", Style::default().fg(Color::Yellow)),
        Span::raw(":connect "),
        Span::styled("s", Style::default().fg(Color::Yellow)),
        Span::raw(":start "),
        Span::styled("x", Style::default().fg(Color::Yellow)),
        Span::raw(":stop "),
        Span::styled("r", Style::default().fg(Color::Yellow)),
        Span::raw(":refresh "),
        Span::styled("g/G", Style::default().fg(Color::Yellow)),
        Span::raw(":top/bot"),
    ];

    let status = if app.status_message.is_empty() {
        keys
    } else {
        let mut v = keys;
        v.push(Span::raw(" | "));
        v.push(Span::styled(
            &app.status_message,
            Style::default().fg(Color::Cyan),
        ));
        v
    };

    let footer = Paragraph::new(Line::from(status))
        .block(
            Block::default()
                .borders(Borders::ALL)
                .border_style(Style::default().fg(Color::DarkGray)),
        )
        .wrap(Wrap { trim: true });
    f.render_widget(footer, area);
}

// ── Event loop ───────────────────────────────────────────────────────────

/// Run the TUI event loop. This is blocking and owns the terminal.
///
/// `refresh_fn` is called whenever a data refresh is needed. It receives
/// the current entries mutably so it can update metrics and push samples.
/// When `refresh_fn` is `None`, the dashboard shows static data (useful for testing).
pub fn run_dashboard<F>(app: &mut DashboardApp, mut refresh_fn: Option<F>) -> Result<()>
where
    F: FnMut(&mut Vec<VmDashboardEntry>),
{
    enable_raw_mode()?;
    io::stdout().execute(EnterAlternateScreen)?;
    let backend = CrosstermBackend::new(io::stdout());
    let mut terminal = Terminal::new(backend)?;

    let result = run_event_loop(&mut terminal, app, &mut refresh_fn);

    disable_raw_mode()?;
    io::stdout().execute(LeaveAlternateScreen)?;
    result
}

fn run_event_loop<F>(
    terminal: &mut Terminal<CrosstermBackend<io::Stdout>>,
    app: &mut DashboardApp,
    refresh_fn: &mut Option<F>,
) -> Result<()>
where
    F: FnMut(&mut Vec<VmDashboardEntry>),
{
    // Initial refresh
    if let Some(ref mut f) = refresh_fn {
        f(&mut app.entries);
        app.mark_refreshed();
    }

    loop {
        terminal.draw(|f| render_dashboard(f, app))?;

        // Poll for events with a short timeout so we can check refresh timer
        let timeout = Duration::from_millis(200);
        if event::poll(timeout)? {
            if let Event::Key(key) = event::read()? {
                app.handle_key(key.code, key.modifiers);
            }
        }

        if app.should_quit {
            break;
        }

        // Handle pending actions -- break out so the caller can execute them
        if app.pending_action.is_some() {
            break;
        }

        // Periodic refresh
        if app.needs_refresh() {
            if let Some(ref mut f) = refresh_fn {
                f(&mut app.entries);
                app.mark_refreshed();
                if !app.status_message.starts_with("Connecting")
                    && !app.status_message.starts_with("Starting")
                    && !app.status_message.starts_with("Stopping")
                {
                    app.status_message.clear();
                }
            }
        }
    }

    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_vm_dashboard_entry_push_sample() {
        let mut entry = VmDashboardEntry::new("test-vm".to_string());
        assert!(entry.cpu_history.is_empty());
        assert!(entry.mem_history.is_empty());

        entry.push_sample(45.0, 60.0);
        assert_eq!(entry.cpu_history.len(), 1);
        assert_eq!(entry.cpu_history[0], 45);
        assert_eq!(entry.mem_history[0], 60);
    }

    #[test]
    fn test_vm_dashboard_entry_push_sample_clamps() {
        let mut entry = VmDashboardEntry::new("test-vm".to_string());
        entry.push_sample(-5.0, 150.0);
        assert_eq!(entry.cpu_history[0], 0);
        assert_eq!(entry.mem_history[0], 100);
    }

    #[test]
    fn test_vm_dashboard_entry_history_capacity() {
        let mut entry = VmDashboardEntry::new("test-vm".to_string());
        for i in 0..HISTORY_CAPACITY + 10 {
            entry.push_sample(i as f32, i as f32);
        }
        assert_eq!(entry.cpu_history.len(), HISTORY_CAPACITY);
        assert_eq!(entry.mem_history.len(), HISTORY_CAPACITY);
        // Oldest should be evicted; first element should be 10
        assert_eq!(entry.cpu_history[0], 10);
    }

    #[test]
    fn test_dashboard_app_navigation() {
        let mut app = DashboardApp::new(5);
        for i in 0..3 {
            app.entries.push(VmDashboardEntry::new(format!("vm-{}", i)));
        }
        app.table_state.select(Some(0));

        // Move down
        app.next();
        assert_eq!(app.selected_index(), Some(1));

        app.next();
        assert_eq!(app.selected_index(), Some(2));

        // Wrap around
        app.next();
        assert_eq!(app.selected_index(), Some(0));

        // Move up wraps
        app.previous();
        assert_eq!(app.selected_index(), Some(2));
    }

    #[test]
    fn test_dashboard_app_first_last() {
        let mut app = DashboardApp::new(5);
        for i in 0..5 {
            app.entries.push(VmDashboardEntry::new(format!("vm-{}", i)));
        }
        app.table_state.select(Some(2));

        app.first();
        assert_eq!(app.selected_index(), Some(0));

        app.last();
        assert_eq!(app.selected_index(), Some(4));
    }

    #[test]
    fn test_handle_key_quit() {
        let mut app = DashboardApp::new(5);
        assert!(!app.should_quit);

        app.handle_key(KeyCode::Char('q'), KeyModifiers::empty());
        assert!(app.should_quit);
    }

    #[test]
    fn test_handle_key_ctrl_c() {
        let mut app = DashboardApp::new(5);
        app.handle_key(KeyCode::Char('c'), KeyModifiers::CONTROL);
        assert!(app.should_quit);
    }

    #[test]
    fn test_handle_key_esc() {
        let mut app = DashboardApp::new(5);
        app.handle_key(KeyCode::Esc, KeyModifiers::empty());
        assert!(app.should_quit);
    }

    #[test]
    fn test_handle_key_navigation() {
        let mut app = DashboardApp::new(5);
        for i in 0..3 {
            app.entries.push(VmDashboardEntry::new(format!("vm-{}", i)));
        }
        app.table_state.select(Some(0));

        app.handle_key(KeyCode::Char('j'), KeyModifiers::empty());
        assert_eq!(app.selected_index(), Some(1));

        app.handle_key(KeyCode::Char('k'), KeyModifiers::empty());
        assert_eq!(app.selected_index(), Some(0));

        app.handle_key(KeyCode::Down, KeyModifiers::empty());
        assert_eq!(app.selected_index(), Some(1));

        app.handle_key(KeyCode::Up, KeyModifiers::empty());
        assert_eq!(app.selected_index(), Some(0));
    }

    #[test]
    fn test_handle_key_actions() {
        let mut app = DashboardApp::new(5);
        app.entries.push(VmDashboardEntry::new("my-vm".to_string()));
        app.table_state.select(Some(0));

        app.handle_key(KeyCode::Enter, KeyModifiers::empty());
        assert!(matches!(app.pending_action, Some(VmAction::Connect(ref n)) if n == "my-vm"));
        app.pending_action = None;

        app.handle_key(KeyCode::Char('s'), KeyModifiers::empty());
        assert!(matches!(app.pending_action, Some(VmAction::Start(ref n)) if n == "my-vm"));
        app.pending_action = None;

        app.handle_key(KeyCode::Char('x'), KeyModifiers::empty());
        assert!(matches!(app.pending_action, Some(VmAction::Stop(ref n)) if n == "my-vm"));
    }

    #[test]
    fn test_handle_key_refresh() {
        let mut app = DashboardApp::new(5);
        app.last_refresh = Instant::now();
        assert!(!app.needs_refresh());

        app.handle_key(KeyCode::Char('r'), KeyModifiers::empty());
        // After 'r' the timer is reset to trigger refresh
        assert!(app.needs_refresh());
    }

    #[test]
    fn test_needs_refresh() {
        let mut app = DashboardApp::new(1);
        app.mark_refreshed();
        assert!(!app.needs_refresh());

        // Simulate time passing
        app.last_refresh = Instant::now() - Duration::from_secs(2);
        assert!(app.needs_refresh());
    }

    #[test]
    fn test_selected_vm_name() {
        let mut app = DashboardApp::new(5);
        assert_eq!(app.selected_vm_name(), None);

        app.entries.push(VmDashboardEntry::new("alpha".to_string()));
        app.entries.push(VmDashboardEntry::new("beta".to_string()));
        app.table_state.select(Some(1));
        assert_eq!(app.selected_vm_name(), Some("beta"));
    }

    #[test]
    fn test_metric_color_thresholds() {
        assert_eq!(metric_color(30.0), Color::Green);
        assert_eq!(metric_color(60.0), Color::Yellow);
        assert_eq!(metric_color(90.0), Color::Red);
    }

    #[test]
    fn test_state_color_values() {
        assert_eq!(state_color("Running"), Color::Green);
        assert_eq!(state_color("running"), Color::Green);
        assert_eq!(state_color("stopped"), Color::Red);
        assert_eq!(state_color("deallocated"), Color::Red);
        assert_eq!(state_color("starting"), Color::Yellow);
    }

    #[test]
    fn test_agent_color_values() {
        assert_eq!(agent_color("OK"), Color::Green);
        assert_eq!(agent_color("Down"), Color::Red);
        assert_eq!(agent_color("N/A"), Color::Yellow);
    }

    #[test]
    fn test_empty_entries_navigation() {
        let mut app = DashboardApp::new(5);
        // Should not panic on empty entries
        app.next();
        app.previous();
        app.first();
        app.last();
        assert_eq!(app.selected_index(), Some(0)); // default
    }
}
