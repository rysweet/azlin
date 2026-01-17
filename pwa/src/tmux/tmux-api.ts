/**
 * Tmux API for Azlin Mobile PWA
 *
 * Provides tmux session management via Azure Run Command API:
 * - List sessions on VM
 * - Capture session snapshots (2000 line limit)
 * - Send keys to sessions
 * - Watch sessions for changes
 *
 * Philosophy:
 * - Single responsibility: Tmux integration
 * - Self-contained with AzureClient dependency
 * - Zero-BS: Real tmux commands via Run Command API
 *
 * Constraints:
 * - 90-second Run Command timeout
 * - 2000-line scrollback limit
 * - Works with private IP VMs via Bastion
 */

import { AzureClient } from '../api/azure-client';

export interface TmuxSession {
  name: string;
  windowCount: number;
  created: Date;
}

export interface TmuxWindow {
  index: number;
  name: string;
  active: boolean;
}

export interface TmuxSnapshot {
  windows: TmuxWindow[];
  activeWindow?: TmuxWindow;
  paneContent: string[];
  timestamp: number;
}

export interface TmuxWatcher {
  start: () => void;
  stop: () => void;
}

export class TmuxApi {
  private azureClient: AzureClient;

  constructor(azureClient: AzureClient) {
    this.azureClient = azureClient;
  }

  /**
   * List all tmux sessions on a VM
   * Uses enhanced format matching azlin CLI for better compatibility
   */
  async listSessions(resourceGroup: string, vmName: string): Promise<TmuxSession[]> {
    // Use enhanced format that matches azlin CLI, with fallback to standard format
    // Enhanced format: name:attached:windows:created (Unix timestamp)
    // Fallback format: name: N windows (created date)
    const script = `tmux list-sessions -F "#{session_name}:#{session_attached}:#{session_windows}:#{session_created}" 2>/dev/null || tmux list-sessions 2>/dev/null || echo ''`;

    try {
      const result = await this.azureClient.executeRunCommand(
        resourceGroup,
        vmName,
        script
      );

      console.log('🏴‍☠️ Tmux list-sessions result:', { exitCode: result.exitCode, stdout: result.stdout, stderr: result.stderr });

      // Parse output regardless of exit code - check content instead
      const output = result.stdout.trim();

      // No sessions: tmux returns error or empty output
      if (!output || output.includes('no server running') || output.includes('error connecting')) {
        return [];
      }

      return this.parseSessions(output);
    } catch (error) {
      const errorMessage = `Failed to list tmux sessions on VM ${vmName} in resource group ${resourceGroup}`;
      const originalError = error instanceof Error ? error.message : String(error);
      throw new Error(`${errorMessage}: ${originalError}`);
    }
  }

  /**
   * Parse tmux list-sessions output
   * Supports both enhanced format (name:attached:windows:created) and standard format
   */
  private parseSessions(output: string): TmuxSession[] {
    const lines = output.trim().split('\n').filter(line => line.length > 0);
    const sessions: TmuxSession[] = [];

    for (const line of lines) {
      // Try enhanced format first: name:attached:windows:created
      const enhancedMatch = line.match(/^([^:]+):(\d+):(\d+):(\d+)$/);
      if (enhancedMatch) {
        const [, name, _attached, windowCount, createdTs] = enhancedMatch;
        sessions.push({
          name: name.trim(),
          windowCount: parseInt(windowCount),
          created: new Date(parseInt(createdTs) * 1000), // Unix timestamp to Date
        });
        continue;
      }

      // Fallback to standard format: "main: 2 windows (created Mon Jan 15 10:00:00 2025)"
      const standardMatch = line.match(/^([^:]+):\s+(\d+)\s+windows?\s+\(created\s+(.+)\)$/);
      if (standardMatch) {
        const [, name, windowCount, created] = standardMatch;
        sessions.push({
          name: name.trim(),
          windowCount: parseInt(windowCount),
          created: new Date(created),
        });
        continue;
      }

      // Try even simpler format: just session name with basic info
      const simpleMatch = line.match(/^([^:]+):\s+(\d+)\s+windows?/);
      if (simpleMatch) {
        const [, name, windowCount] = simpleMatch;
        sessions.push({
          name: name.trim(),
          windowCount: parseInt(windowCount),
          created: new Date(), // Unknown, use now
        });
      }
    }

    console.log('🏴‍☠️ Parsed tmux sessions:', sessions);
    return sessions;
  }

  /**
   * Capture tmux session snapshot (2000 lines max)
   */
  async captureSnapshot(
    resourceGroup: string,
    vmName: string,
    sessionName: string
  ): Promise<TmuxSnapshot> {
    // Escape shell special characters in sessionName
    const escapeShellArg = (arg: string): string => {
      // Replace single quotes with '\'' (end quote, escaped quote, start quote)
      return `'${arg.replace(/'/g, "'\\''")}'`;
    };

    const escapedSessionName = escapeShellArg(sessionName);

    const script = `
      # Check if session exists
      tmux has-session -t ${escapedSessionName} 2>/dev/null || exit 1

      # Get session info
      echo "SESSION_INFO:"
      tmux list-windows -t ${escapedSessionName} -F "#{window_index}:#{window_name}:#{window_active}"

      echo "PANE_CONTENT:"
      # Capture active pane (2000 lines of scrollback)
      tmux capture-pane -t ${escapedSessionName} -p -S -2000
    `.trim();

    const result = await this.azureClient.executeRunCommand(
      resourceGroup,
      vmName,
      script
    );

    if (result.exitCode !== 0) {
      throw new Error(`Failed to capture snapshot: ${result.stderr}`);
    }

    return this.parseSnapshot(result.stdout);
  }

  /**
   * Parse tmux snapshot output
   */
  private parseSnapshot(output: string): TmuxSnapshot {
    const lines = output.split('\n');
    const sessionInfoIndex = lines.indexOf('SESSION_INFO:');
    const paneContentIndex = lines.indexOf('PANE_CONTENT:');

    if (sessionInfoIndex === -1 || paneContentIndex === -1) {
      throw new Error('Invalid snapshot format');
    }

    // Parse windows
    const windows = lines
      .slice(sessionInfoIndex + 1, paneContentIndex)
      .filter(line => line.trim().length > 0)
      .map(line => {
        const [index, name, active] = line.split(':');
        return {
          index: parseInt(index),
          name,
          active: active === '1',
        };
      });

    // Parse pane content (limit to 2000 lines)
    const paneContent = lines
      .slice(paneContentIndex + 1)
      .slice(0, 2000);

    const activeWindow = windows.find(w => w.active);

    return {
      windows,
      activeWindow,
      paneContent,
      timestamp: Date.now(),
    };
  }

  /**
   * Send keys to tmux session
   */
  async sendKeys(
    resourceGroup: string,
    vmName: string,
    sessionName: string,
    keys: string
  ): Promise<{ success: boolean }> {
    if (!keys || keys.trim().length === 0) {
      throw new Error('Keys cannot be empty');
    }

    // Escape shell special characters for both sessionName and keys
    // Use single quotes and escape any single quotes in the content
    const escapeShellArg = (arg: string): string => {
      // Replace single quotes with '\'' (end quote, escaped quote, start quote)
      return `'${arg.replace(/'/g, "'\\''")}'`;
    };

    const escapedSessionName = escapeShellArg(sessionName);
    const escapedKeys = escapeShellArg(keys);

    const script = `
      # Send keys to active pane
      tmux send-keys -t ${escapedSessionName} ${escapedKeys}
    `.trim();

    const result = await this.azureClient.executeRunCommand(
      resourceGroup,
      vmName,
      script
    );

    if (result.exitCode !== 0) {
      throw new Error(`Failed to send keys: ${result.stderr}`);
    }

    return { success: true };
  }

  /**
   * Watch tmux session for changes
   */
  watchSession(
    resourceGroup: string,
    vmName: string,
    sessionName: string,
    onChangeCallback: (diff: { hasChanges: boolean; changedLines: any[] }) => void,
    interval: number = 10000
  ): TmuxWatcher {
    let intervalId: number | null = null;
    let lastSnapshot: TmuxSnapshot | null = null;

    const start = () => {
      intervalId = window.setInterval(async () => {
        try {
          const snapshot = await this.captureSnapshot(
            resourceGroup,
            vmName,
            sessionName
          );

          if (lastSnapshot) {
            const diff = this.computeDiff(lastSnapshot, snapshot);
            if (diff.hasChanges) {
              onChangeCallback(diff);
            }
          }

          lastSnapshot = snapshot;
        } catch (error) {
          console.error('Watch session error:', error);
        }
      }, interval);
    };

    const stop = () => {
      if (intervalId !== null) {
        window.clearInterval(intervalId);
        intervalId = null;
      }
    };

    return { start, stop };
  }

  /**
   * Compute diff between two snapshots
   */
  private computeDiff(
    oldSnapshot: TmuxSnapshot,
    newSnapshot: TmuxSnapshot
  ): { hasChanges: boolean; changedLines: any[] } {
    const changedLines: any[] = [];

    const maxLength = Math.max(
      oldSnapshot.paneContent.length,
      newSnapshot.paneContent.length
    );

    for (let i = 0; i < maxLength; i++) {
      const oldLine = oldSnapshot.paneContent[i] || '';
      const newLine = newSnapshot.paneContent[i] || '';

      if (oldLine !== newLine) {
        changedLines.push({
          lineNumber: i,
          oldContent: oldLine,
          newContent: newLine,
        });
      }
    }

    return {
      hasChanges: changedLines.length > 0,
      changedLines,
    };
  }
}

export default TmuxApi;
