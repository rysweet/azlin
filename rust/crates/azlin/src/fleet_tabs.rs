//! Fleet run output with per-VM tab panels using ratatui.

use std::io::IsTerminal;
use crossterm::{event::{self, Event, KeyCode}, terminal::{disable_raw_mode, enable_raw_mode, EnterAlternateScreen, LeaveAlternateScreen}, ExecutableCommand};
use ratatui::{backend::CrosstermBackend, layout::{Constraint, Direction, Layout}, style::{Color, Modifier, Style}, text::{Line, Span}, widgets::{Block, Borders, Paragraph, Tabs, Wrap}, Terminal};

#[derive(Debug, Clone)]
pub struct VmOutput { pub vm_name: String, pub exit_code: i32, pub stdout: String, pub stderr: String }

impl VmOutput {
    pub fn succeeded(&self) -> bool { self.exit_code == 0 }
    pub fn combined_output(&self) -> String {
        let mut o = self.stdout.clone();
        if !self.stderr.is_empty() { if !o.is_empty() { o.push('\n'); } o.push_str(&self.stderr); }
        o
    }
    pub fn status_icon(&self) -> &'static str { if self.succeeded() { "\u{2713}" } else { "\u{2717}" } }
}

struct FleetTabsState { outputs: Vec<VmOutput>, active_tab: usize, scroll_offset: u16, show_summary: bool }

impl FleetTabsState {
    fn new(outputs: Vec<VmOutput>) -> Self { Self { outputs, active_tab: 0, scroll_offset: 0, show_summary: false } }
    fn next_tab(&mut self) { if !self.outputs.is_empty() { self.active_tab = (self.active_tab + 1) % self.outputs.len(); self.scroll_offset = 0; } }
    fn prev_tab(&mut self) { if !self.outputs.is_empty() { self.active_tab = if self.active_tab == 0 { self.outputs.len() - 1 } else { self.active_tab - 1 }; self.scroll_offset = 0; } }
    fn scroll_down(&mut self) { self.scroll_offset = self.scroll_offset.saturating_add(1); }
    fn scroll_up(&mut self) { self.scroll_offset = self.scroll_offset.saturating_sub(1); }
}

pub fn run_fleet_tabs(outputs: Vec<VmOutput>, no_tui: bool) -> anyhow::Result<()> {
    if no_tui || !std::io::stdout().is_terminal() { print_plain_output(&outputs); return Ok(()); }
    enable_raw_mode()?;
    std::io::stdout().execute(EnterAlternateScreen)?;
    let backend = CrosstermBackend::new(std::io::stdout());
    let mut terminal = Terminal::new(backend)?;
    let mut state = FleetTabsState::new(outputs);
    let result = run_tabs_loop(&mut terminal, &mut state);
    disable_raw_mode()?;
    std::io::stdout().execute(LeaveAlternateScreen)?;
    result
}

fn run_tabs_loop(terminal: &mut Terminal<CrosstermBackend<std::io::Stdout>>, state: &mut FleetTabsState) -> anyhow::Result<()> {
    loop {
        terminal.draw(|f| render_tabs(f, state))?;
        if event::poll(std::time::Duration::from_millis(100))? {
            if let Event::Key(key) = event::read()? {
                match key.code {
                    KeyCode::Char('q') | KeyCode::Esc => break,
                    KeyCode::Right | KeyCode::Tab => state.next_tab(),
                    KeyCode::Left | KeyCode::BackTab => state.prev_tab(),
                    KeyCode::Down | KeyCode::Char('j') => state.scroll_down(),
                    KeyCode::Up | KeyCode::Char('k') => state.scroll_up(),
                    KeyCode::Char('s') => state.show_summary = !state.show_summary,
                    KeyCode::Char(c) if c.is_ascii_digit() => {
                        let idx = c.to_digit(10).unwrap_or(0) as usize;
                        let target = if idx == 0 { 9 } else { idx - 1 };
                        if target < state.outputs.len() { state.active_tab = target; state.scroll_offset = 0; }
                    }
                    _ => {}
                }
            }
        }
    }
    Ok(())
}

fn render_tabs(f: &mut ratatui::Frame, state: &FleetTabsState) {
    let chunks = Layout::default().direction(Direction::Vertical)
        .constraints([Constraint::Length(3), Constraint::Min(5), Constraint::Length(3)]).split(f.area());
    // Tab bar
    let titles: Vec<Line> = state.outputs.iter().enumerate().map(|(i, vm)| {
        let c = if vm.succeeded() { Color::Green } else { Color::Red };
        let num = if i < 9 { format!("{}", i + 1) } else { " ".into() };
        Line::from(vec![Span::styled(format!(" {} ", vm.status_icon()), Style::default().fg(c)), Span::raw(format!("{}: {} ", num, vm.vm_name))])
    }).collect();
    let tabs = Tabs::new(titles).select(state.active_tab)
        .block(Block::default().borders(Borders::ALL).title(" Fleet Output "))
        .highlight_style(Style::default().fg(Color::Cyan).add_modifier(Modifier::BOLD)).divider("|");
    f.render_widget(tabs, chunks[0]);
    // Content
    if state.show_summary {
        let mut lines = vec![Line::from(vec![
            Span::styled(format!(" {} ok ", state.outputs.iter().filter(|v| v.succeeded()).count()), Style::default().fg(Color::Green)),
            Span::raw(" | "),
            Span::styled(format!(" {} fail ", state.outputs.iter().filter(|v| !v.succeeded()).count()), Style::default().fg(Color::Red)),
        ]), Line::from("")];
        for vm in &state.outputs {
            let (icon, c) = if vm.succeeded() { ("\u{2713}", Color::Green) } else { ("\u{2717}", Color::Red) };
            lines.push(Line::from(vec![Span::styled(format!(" {} ", icon), Style::default().fg(c)), Span::raw(format!("{:<20} exit: {}", vm.vm_name, vm.exit_code))]));
        }
        f.render_widget(Paragraph::new(lines).block(Block::default().borders(Borders::ALL).title(" Summary ")).wrap(Wrap { trim: false }), chunks[1]);
    } else if !state.outputs.is_empty() {
        let vm = &state.outputs[state.active_tab];
        let status = if vm.succeeded() { "success".into() } else { format!("exit {}", vm.exit_code) };
        f.render_widget(Paragraph::new(vm.combined_output())
            .block(Block::default().borders(Borders::ALL).title(format!(" {} - {} ", vm.vm_name, status)))
            .wrap(Wrap { trim: false }).scroll((state.scroll_offset, 0)), chunks[1]);
    }
    // Footer
    let toggle = if state.show_summary { "output" } else { "summary" };
    f.render_widget(Block::default().title(format!(" q: quit | <-/->: tabs | 1-9: jump | s: {} | j/k: scroll ", toggle))
        .borders(Borders::ALL).border_style(Style::default().fg(Color::DarkGray)), chunks[2]);
}

pub fn print_plain_output(outputs: &[VmOutput]) {
    for vm in outputs {
        println!("--- {} {} (exit: {}) ---", vm.status_icon(), vm.vm_name, vm.exit_code);
        let c = vm.combined_output(); if !c.is_empty() { println!("{}", c); }
        println!();
    }
    let ok = outputs.iter().filter(|v| v.succeeded()).count();
    println!("Summary: {} succeeded, {} failed out of {} VMs", ok, outputs.len() - ok, outputs.len());
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sample() -> Vec<VmOutput> {
        vec![
            VmOutput { vm_name: "vm-1".into(), exit_code: 0, stdout: "hello\n".into(), stderr: String::new() },
            VmOutput { vm_name: "vm-2".into(), exit_code: 1, stdout: String::new(), stderr: "err\n".into() },
            VmOutput { vm_name: "vm-3".into(), exit_code: 0, stdout: "out\n".into(), stderr: "warn\n".into() },
        ]
    }

    #[test] fn test_succeeded() { assert!(sample()[0].succeeded()); assert!(!sample()[1].succeeded()); }
    #[test] fn test_combined_output() { assert!(sample()[2].combined_output().contains("out")); assert!(sample()[2].combined_output().contains("warn")); }
    #[test] fn test_status_icon() { assert_eq!(sample()[0].status_icon(), "\u{2713}"); assert_eq!(sample()[1].status_icon(), "\u{2717}"); }
    #[test] fn test_navigation() {
        let mut s = FleetTabsState::new(sample());
        assert_eq!(s.active_tab, 0);
        s.next_tab(); assert_eq!(s.active_tab, 1);
        s.next_tab(); assert_eq!(s.active_tab, 2);
        s.next_tab(); assert_eq!(s.active_tab, 0);
        s.prev_tab(); assert_eq!(s.active_tab, 2);
    }
    #[test] fn test_scroll() {
        let mut s = FleetTabsState::new(sample());
        s.scroll_down(); assert_eq!(s.scroll_offset, 1);
        s.scroll_up(); assert_eq!(s.scroll_offset, 0);
        s.scroll_up(); assert_eq!(s.scroll_offset, 0); // no underflow
    }
}
