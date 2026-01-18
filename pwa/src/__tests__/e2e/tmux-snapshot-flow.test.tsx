/**
 * E2E Test: Tmux Snapshot Capture Workflow (10% of testing pyramid)
 *
 * Tests complete user workflow for viewing tmux sessions.
 * These tests WILL FAIL until all components are implemented.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { Provider } from 'react-redux';
import { configureStore } from '@reduxjs/toolkit';
import { BrowserRouter } from 'react-router-dom';
import VMDetailPage from '../../pages/VMDetailPage';
import vmReducer from '../../store/vm-store';
import tmuxReducer from '../../store/tmux-store';
import authReducer from '../../store/auth-store';

function renderWithAuth(component: React.ReactElement) {
  const store = configureStore({
    reducer: {
      vms: vmReducer,
      tmux: tmuxReducer,
      auth: authReducer,
    },
    preloadedState: {
      auth: {
        isAuthenticated: true,
        loading: false,
        error: null,
        deviceCode: null,
        pollingIntervalId: null,
      },
    },
  });

  return render(
    <Provider store={store}>
      <BrowserRouter>
        {component}
      </BrowserRouter>
    </Provider>
  );
}

describe('E2E: Tmux Snapshot Workflow', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('should display tmux sessions for a VM', async () => {
    renderWithAuth(<VMDetailPage />);

    // Navigate to tmux tab
    const tmuxTab = screen.getByRole('tab', { name: /tmux sessions/i });
    await userEvent.click(tmuxTab);

    // Should show loading indicator
    expect(screen.getByText(/loading sessions/i)).toBeDefined();

    // Wait for sessions to load
    await waitFor(() => {
      const sessionList = screen.getByRole('list', { name: /tmux sessions/i });
      expect(sessionList).toBeDefined();
    }, { timeout: 10000 });

    // Should show session names
    const sessions = screen.getAllByRole('listitem');
    expect(sessions.length).toBeGreaterThan(0);
    // Will fail until implemented
  });

  it('should capture and display session snapshot', async () => {
    renderWithAuth(<VMDetailPage />);

    const tmuxTab = screen.getByRole('tab', { name: /tmux sessions/i });
    await userEvent.click(tmuxTab);

    await waitFor(() => {
      screen.getByRole('list', { name: /tmux sessions/i });
    });

    // Click on first session
    const sessions = screen.getAllByRole('listitem');
    const firstSession = sessions[0];

    await userEvent.click(firstSession);

    // Should show snapshot loading
    await waitFor(() => {
      const loading = screen.getByText(/capturing snapshot/i);
      expect(loading).toBeDefined();
    });

    // Should display snapshot content
    await waitFor(
      () => {
        const snapshotView = screen.getByRole('region', { name: /snapshot/i });
        expect(snapshotView).toBeDefined();
      },
      { timeout: 30000 } // Run Command can take time
    );

    // Should show pane content
    const terminalOutput = screen.getByRole('code');
    expect(terminalOutput).toBeDefined();
  });

  it('should show window tabs for multi-window sessions', async () => {
    renderWithAuth(<VMDetailPage />);

    const tmuxTab = screen.getByRole('tab', { name: /tmux sessions/i });
    await userEvent.click(tmuxTab);

    await waitFor(() => {
      screen.getByRole('list', { name: /tmux sessions/i });
    });

    const sessions = screen.getAllByRole('listitem');
    const firstSession = sessions[0];
    await userEvent.click(firstSession);

    await waitFor(() => {
      screen.getByRole('region', { name: /snapshot/i });
    });

    // Should show window tabs
    const windowTabs = screen.getAllByRole('tab', { name: /window \d+/i });
    expect(windowTabs.length).toBeGreaterThan(0);

    // Active window should be highlighted
    const activeWindow = windowTabs.find(tab =>
      tab.getAttribute('aria-selected') === 'true'
    );
    expect(activeWindow).toBeDefined();
  });

  it('should send keys to tmux session', async () => {
    renderWithAuth(<VMDetailPage />);

    const tmuxTab = screen.getByRole('tab', { name: /tmux sessions/i });
    await userEvent.click(tmuxTab);

    await waitFor(() => {
      screen.getByRole('list', { name: /tmux sessions/i });
    });

    const sessions = screen.getAllByRole('listitem');
    await userEvent.click(sessions[0]);

    await waitFor(() => {
      screen.getByRole('region', { name: /snapshot/i });
    });

    // Should show command input
    const commandInput = screen.getByRole('textbox', {
      name: /send command/i,
    });
    expect(commandInput).toBeDefined();

    // Type a command
    await userEvent.type(commandInput, 'ls -la');

    // Click send button
    const sendButton = screen.getByRole('button', { name: /send/i });
    await userEvent.click(sendButton);

    // Should show sending indicator
    await waitFor(() => {
      expect(screen.getByText(/sending/i)).toBeDefined();
    });

    // Should clear input after sending
    await waitFor(() => {
      expect(commandInput).toHaveValue('');
    });

    // Should show success feedback
    await waitFor(() => {
      const successMessage = screen.getByText(/command sent/i);
      expect(successMessage).toBeDefined();
    });
  });

  it('should handle Enter key shortcut for sending commands', async () => {
    renderWithAuth(<VMDetailPage />);

    const tmuxTab = screen.getByRole('tab', { name: /tmux sessions/i });
    await userEvent.click(tmuxTab);

    await waitFor(() => {
      screen.getByRole('list', { name: /tmux sessions/i });
    });

    const sessions = screen.getAllByRole('listitem');
    await userEvent.click(sessions[0]);

    await waitFor(() => {
      screen.getByRole('region', { name: /snapshot/i });
    });

    const commandInput = screen.getByRole('textbox', {
      name: /send command/i,
    });

    // Type command and press Enter
    await userEvent.type(commandInput, 'echo "test"{Enter}');

    // Should send command without clicking button
    await waitFor(() => {
      expect(screen.getByText(/command sent/i)).toBeDefined();
    });
  });

  it('should enable watch mode for live updates', async () => {
    vi.useFakeTimers();

    renderWithAuth(<VMDetailPage />);

    const tmuxTab = screen.getByRole('tab', { name: /tmux sessions/i });
    await userEvent.click(tmuxTab);

    await waitFor(() => {
      screen.getByRole('list', { name: /tmux sessions/i });
    });

    const sessions = screen.getAllByRole('listitem');
    await userEvent.click(sessions[0]);

    await waitFor(() => {
      screen.getByRole('region', { name: /snapshot/i });
    });

    // Enable watch mode
    const watchToggle = screen.getByRole('switch', { name: /watch mode/i });
    await userEvent.click(watchToggle);

    // Should show watch indicator
    expect(screen.getByText(/watching/i)).toBeDefined();

    // Should poll at 10 second interval
    vi.advanceTimersByTime(10000);

    // Should show last updated time
    await waitFor(() => {
      const lastUpdate = screen.getByText(/updated \d+ seconds? ago/i);
      expect(lastUpdate).toBeDefined();
    });

    vi.useRealTimers();
  });

  it('should highlight changed lines in watch mode', async () => {
    vi.useFakeTimers();

    renderWithAuth(<VMDetailPage />);

    const tmuxTab = screen.getByRole('tab', { name: /tmux sessions/i });
    await userEvent.click(tmuxTab);

    await waitFor(() => {
      screen.getByRole('list', { name: /tmux sessions/i });
    });

    const sessions = screen.getAllByRole('listitem');
    await userEvent.click(sessions[0]);

    await waitFor(() => {
      screen.getByRole('region', { name: /snapshot/i });
    });

    const watchToggle = screen.getByRole('switch', { name: /watch mode/i });
    await userEvent.click(watchToggle);

    // Advance time for next poll
    vi.advanceTimersByTime(10000);

    // Should highlight changed lines
    await waitFor(() => {
      const highlightedLines = screen.getAllByRole('listitem', { name: /changed/i });
      expect(highlightedLines.length).toBeGreaterThan(0);
    });

    vi.useRealTimers();
  });

  it('should show scrollback with 2000 line limit', async () => {
    renderWithAuth(<VMDetailPage />);

    const tmuxTab = screen.getByRole('tab', { name: /tmux sessions/i });
    await userEvent.click(tmuxTab);

    await waitFor(() => {
      screen.getByRole('list', { name: /tmux sessions/i });
    });

    const sessions = screen.getAllByRole('listitem');
    await userEvent.click(sessions[0]);

    await waitFor(() => {
      screen.getByRole('region', { name: /snapshot/i });
    });

    // Should show line count
    const lineCount = screen.getByText(/\d+ lines/i);
    expect(lineCount).toBeDefined();

    // Extract number
    const match = lineCount.textContent?.match(/(\d+) lines/i);
    if (match) {
      const lines = parseInt(match[1]);
      expect(lines).toBeLessThanOrEqual(2000);
    }
  });

  it('should handle snapshot timeout (90 seconds)', async () => {
    vi.useFakeTimers();

    // Mock long-running Run Command
    vi.spyOn(global, 'fetch').mockImplementation(() =>
      new Promise(resolve => {
        setTimeout(
          () =>
            resolve({
              ok: false,
              status: 408,
              statusText: 'Request Timeout',
            } as Response),
          91000
        );
      })
    );

    renderWithAuth(<VMDetailPage />);

    const tmuxTab = screen.getByRole('tab', { name: /tmux sessions/i });
    await userEvent.click(tmuxTab);

    await waitFor(() => {
      screen.getByRole('list', { name: /tmux sessions/i });
    });

    const sessions = screen.getAllByRole('listitem');
    await userEvent.click(sessions[0]);

    // Advance past timeout
    vi.advanceTimersByTime(95000);

    // Should show timeout error
    await waitFor(() => {
      const errorMessage = screen.getByText(/timeout/i);
      expect(errorMessage).toBeDefined();
    });

    vi.useRealTimers();
  });

  it('should work with private IP VMs via Azure Bastion', async () => {
    // VMs with private IPs should work via Run Command API
    renderWithAuth(<VMDetailPage />);

    const tmuxTab = screen.getByRole('tab', { name: /tmux sessions/i });
    await userEvent.click(tmuxTab);

    await waitFor(() => {
      screen.getByRole('list', { name: /tmux sessions/i });
    });

    // Should show private IP indicator
    const privateIPIndicator = screen.getByText(/private network/i);
    expect(privateIPIndicator).toBeDefined();

    // Should still be able to capture snapshots
    const sessions = screen.getAllByRole('listitem');
    await userEvent.click(sessions[0]);

    await waitFor(() => {
      const snapshotView = screen.getByRole('region', { name: /snapshot/i });
      expect(snapshotView).toBeDefined();
    });
  });

  it('should support copy snapshot content to clipboard', async () => {
    // Mock clipboard API
    Object.assign(navigator, {
      clipboard: {
        writeText: vi.fn().mockResolvedValue(undefined),
      },
    });

    renderWithAuth(<VMDetailPage />);

    const tmuxTab = screen.getByRole('tab', { name: /tmux sessions/i });
    await userEvent.click(tmuxTab);

    await waitFor(() => {
      screen.getByRole('list', { name: /tmux sessions/i });
    });

    const sessions = screen.getAllByRole('listitem');
    await userEvent.click(sessions[0]);

    await waitFor(() => {
      screen.getByRole('region', { name: /snapshot/i });
    });

    // Click copy button
    const copyButton = screen.getByRole('button', { name: /copy/i });
    await userEvent.click(copyButton);

    // Should call clipboard API
    expect(navigator.clipboard.writeText).toHaveBeenCalled();

    // Should show success feedback
    await waitFor(() => {
      const copiedMessage = screen.getByText(/copied/i);
      expect(copiedMessage).toBeDefined();
    });
  });
});
