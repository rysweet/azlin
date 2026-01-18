/**
 * Unit Tests for Tmux API (60% of testing pyramid)
 *
 * Tests tmux integration via Azure Run Command API.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { TmuxApi } from '../tmux-api';

// Mock AzureClient
vi.mock('../../api/azure-client');

describe('TmuxApi', () => {
  let tmuxApi: TmuxApi;
  let mockAzureClient: any;

  beforeEach(() => {
    mockAzureClient = {
      executeRunCommand: vi.fn(),
    };
    tmuxApi = new TmuxApi(mockAzureClient);
  });

  describe('listSessions', () => {
    it('should list all tmux sessions on VM', async () => {
      mockAzureClient.executeRunCommand.mockResolvedValue({
        exitCode: 0,
        stdout: 'main: 2 windows (created Mon Jan 15 10:00:00 2025)\ndev: 1 windows (created Mon Jan 15 10:05:00 2025)',
        stderr: '',
      });

      const sessions = await tmuxApi.listSessions('rg-test', 'vm-test-1');

      expect(sessions).toHaveLength(2);
      expect(sessions[0].name).toBe('main');
      expect(sessions[1].name).toBe('dev');
      // Will fail until implemented
    });

    it('should parse session window count', async () => {
      mockAzureClient.executeRunCommand.mockResolvedValue({
        exitCode: 0,
        stdout: 'main: 3 windows (created Mon Jan 15 10:00:00 2025)',
        stderr: '',
      });

      const sessions = await tmuxApi.listSessions('rg-test', 'vm-test-1');

      expect(sessions[0].windowCount).toBe(3);
    });

    it('should parse session creation time', async () => {
      mockAzureClient.executeRunCommand.mockResolvedValue({
        exitCode: 0,
        stdout: 'main: 2 windows (created Mon Jan 15 10:00:00 2025)',
        stderr: '',
      });

      const sessions = await tmuxApi.listSessions('rg-test', 'vm-test-1');

      expect(sessions[0].created).toBeDefined();
      expect(sessions[0].created).toBeInstanceOf(Date);
    });

    it('should handle no sessions', async () => {
      mockAzureClient.executeRunCommand.mockResolvedValue({
        exitCode: 1,
        stdout: '',
        stderr: 'no server running on /tmp/tmux-1000/default',
      });

      const sessions = await tmuxApi.listSessions('rg-test', 'vm-test-1');

      expect(sessions).toEqual([]);
    });

    it('should handle VM connection error', async () => {
      mockAzureClient.executeRunCommand.mockRejectedValue(
        new Error('Connection timeout')
      );

      await expect(
        tmuxApi.listSessions('rg-test', 'vm-test-1')
      ).rejects.toThrow('Connection timeout');
    });
  });

  describe('captureSnapshot', () => {
    it('should capture tmux session snapshot', async () => {
      mockAzureClient.executeRunCommand.mockResolvedValue({
        exitCode: 0,
        stdout: `SESSION_INFO:
0:main:1
1:editor:0
PANE_CONTENT:
$ ls -la
total 48
-rw-r--r-- 1 user user 1234 Jan 15 10:00 file.txt`,
        stderr: '',
      });

      const snapshot = await tmuxApi.captureSnapshot('rg-test', 'vm-test-1', 'main');

      expect(snapshot).toBeDefined();
      expect(snapshot.windows).toBeDefined();
      expect(snapshot.paneContent).toBeDefined();
      expect(snapshot.timestamp).toBeDefined();
      // Will fail until implemented
    });

    it('should parse window information', async () => {
      mockAzureClient.executeRunCommand.mockResolvedValue({
        exitCode: 0,
        stdout: `SESSION_INFO:
0:main:1
1:editor:0
PANE_CONTENT:
content here`,
        stderr: '',
      });

      const snapshot = await tmuxApi.captureSnapshot('rg-test', 'vm-test-1', 'main');

      expect(snapshot.windows).toHaveLength(2);
      expect(snapshot.windows[0]).toEqual({
        index: 0,
        name: 'main',
        active: true,
      });
      expect(snapshot.windows[1]).toEqual({
        index: 1,
        name: 'editor',
        active: false,
      });
    });

    it('should identify active window', async () => {
      mockAzureClient.executeRunCommand.mockResolvedValue({
        exitCode: 0,
        stdout: `SESSION_INFO:
0:main:1
PANE_CONTENT:
content`,
        stderr: '',
      });

      const snapshot = await tmuxApi.captureSnapshot('rg-test', 'vm-test-1', 'main');

      expect(snapshot.activeWindow).toBeDefined();
      expect(snapshot.activeWindow?.name).toBe('main');
      expect(snapshot.activeWindow?.active).toBe(true);
    });

    it('should parse pane content as array of lines', async () => {
      mockAzureClient.executeRunCommand.mockResolvedValue({
        exitCode: 0,
        stdout: `SESSION_INFO:
0:main:1
PANE_CONTENT:
line 1
line 2
line 3`,
        stderr: '',
      });

      const snapshot = await tmuxApi.captureSnapshot('rg-test', 'vm-test-1', 'main');

      expect(snapshot.paneContent).toBeInstanceOf(Array);
      expect(snapshot.paneContent).toHaveLength(3);
      expect(snapshot.paneContent[0]).toBe('line 1');
    });

    it('should handle session not found', async () => {
      mockAzureClient.executeRunCommand.mockResolvedValue({
        exitCode: 1,
        stdout: '',
        stderr: "session not found: nonexistent",
      });

      await expect(
        tmuxApi.captureSnapshot('rg-test', 'vm-test-1', 'nonexistent')
      ).rejects.toThrow('session not found');
    });

    it('should capture up to 2000 lines of scrollback', async () => {
      const longOutput = 'line\n'.repeat(2500);
      mockAzureClient.executeRunCommand.mockResolvedValue({
        exitCode: 0,
        stdout: `SESSION_INFO:
0:main:1
PANE_CONTENT:
${longOutput}`,
        stderr: '',
      });

      const snapshot = await tmuxApi.captureSnapshot('rg-test', 'vm-test-1', 'main');

      // Should be capped at 2000 lines
      expect(snapshot.paneContent.length).toBeLessThanOrEqual(2000);
    });

    it('should use tr to strip non-printable characters', async () => {
      mockAzureClient.executeRunCommand.mockResolvedValue({
        exitCode: 0,
        stdout: `SESSION_INFO:
0:main:1
PANE_CONTENT:
normal text here`,
        stderr: '',
      });

      await tmuxApi.captureSnapshot('rg-test', 'vm-test-1', 'main');

      // Verify the script uses tr to strip non-printable chars while preserving text
      const callArgs = mockAzureClient.executeRunCommand.mock.calls[0];
      expect(callArgs[0]).toBe('rg-test');
      expect(callArgs[1]).toBe('vm-test-1');
      expect(callArgs[2]).toContain('tr -cd');
      expect(callArgs[2]).toContain('[:print:][:space:]');
    });

    it('should gracefully handle missing markers and return raw content', async () => {
      // Simulate output where markers are not present (e.g., corrupted output)
      mockAzureClient.executeRunCommand.mockResolvedValue({
        exitCode: 0,
        stdout: `some raw terminal content
without proper markers
line 3`,
        stderr: '',
      });

      const snapshot = await tmuxApi.captureSnapshot('rg-test', 'vm-test-1', 'main');

      // Should still return something usable
      expect(snapshot).toBeDefined();
      expect(snapshot.paneContent.length).toBeGreaterThan(0);
      expect(snapshot.windows).toEqual([]);
    });
  });

  describe('sendKeys', () => {
    it('should send keys to tmux session', async () => {
      mockAzureClient.executeRunCommand.mockResolvedValue({
        exitCode: 0,
        stdout: 'Keys sent successfully',
        stderr: '',
      });

      const result = await tmuxApi.sendKeys('rg-test', 'vm-test-1', 'main', 'ls -la');

      expect(result.success).toBe(true);
      // Will fail until implemented
    });

    it('should automatically append Enter key to execute commands', async () => {
      mockAzureClient.executeRunCommand.mockResolvedValue({
        exitCode: 0,
        stdout: '',
        stderr: '',
      });

      const result = await tmuxApi.sendKeys('rg-test', 'vm-test-1', 'main', 'ls -la');

      expect(result.success).toBe(true);
      // Verify the script ends with 'Enter' to execute the command
      expect(mockAzureClient.executeRunCommand).toHaveBeenCalledWith(
        'rg-test',
        'vm-test-1',
        expect.stringMatching(/Enter'$/)
      );
    });

    it('should escape single quotes in session name and keys', async () => {
      mockAzureClient.executeRunCommand.mockResolvedValue({
        exitCode: 0,
        stdout: '',
        stderr: '',
      });

      await tmuxApi.sendKeys('rg-test', 'vm-test-1', "test's session", "echo 'hello'");

      // Should be called without error - escaping handled internally
      expect(mockAzureClient.executeRunCommand).toHaveBeenCalled();
    });

    it('should handle session not found', async () => {
      mockAzureClient.executeRunCommand.mockResolvedValue({
        exitCode: 1,
        stdout: '',
        stderr: 'session not found: nonexistent',
      });

      await expect(
        tmuxApi.sendKeys('rg-test', 'vm-test-1', 'nonexistent', 'test')
      ).rejects.toThrow();
    });

    it('should validate keys parameter is not empty', async () => {
      await expect(
        tmuxApi.sendKeys('rg-test', 'vm-test-1', 'main', '')
      ).rejects.toThrow('Keys cannot be empty');
    });
  });

  describe('watchSession', () => {
    it('should create session watcher with callback', () => {
      const callback = vi.fn();

      const watcher = tmuxApi.watchSession(
        'rg-test',
        'vm-test-1',
        'main',
        callback
      );

      expect(watcher).toBeDefined();
      expect(watcher.start).toBeInstanceOf(Function);
      expect(watcher.stop).toBeInstanceOf(Function);
      // Will fail until implemented
    });

    it('should poll session at specified interval', async () => {
      vi.useFakeTimers();
      const callback = vi.fn();

      mockAzureClient.executeRunCommand.mockResolvedValue({
        exitCode: 0,
        stdout: 'SESSION_INFO:\n0:main:1\nPANE_CONTENT:\ncontent',
        stderr: '',
      });

      const watcher = tmuxApi.watchSession(
        'rg-test',
        'vm-test-1',
        'main',
        callback,
        5000 // 5 second interval
      );

      watcher.start();

      // Advance timer by 5 seconds
      await vi.advanceTimersByTimeAsync(5000);

      expect(mockAzureClient.executeRunCommand).toHaveBeenCalled();

      watcher.stop();
      vi.useRealTimers();
    });

    it('should detect content changes', async () => {
      vi.useFakeTimers();
      const callback = vi.fn();

      mockAzureClient.executeRunCommand
        .mockResolvedValueOnce({
          exitCode: 0,
          stdout: 'SESSION_INFO:\n0:main:1\nPANE_CONTENT:\nold content',
          stderr: '',
        })
        .mockResolvedValueOnce({
          exitCode: 0,
          stdout: 'SESSION_INFO:\n0:main:1\nPANE_CONTENT:\nnew content',
          stderr: '',
        });

      const watcher = tmuxApi.watchSession('rg-test', 'vm-test-1', 'main', callback);
      watcher.start();

      await vi.advanceTimersByTimeAsync(20000); // Two intervals

      expect(callback).toHaveBeenCalledWith(
        expect.objectContaining({
          hasChanges: true,
        })
      );

      watcher.stop();
      vi.useRealTimers();
    });

    it('should not trigger callback when content unchanged', async () => {
      vi.useFakeTimers();
      const callback = vi.fn();

      mockAzureClient.executeRunCommand.mockResolvedValue({
        exitCode: 0,
        stdout: 'SESSION_INFO:\n0:main:1\nPANE_CONTENT:\nsame content',
        stderr: '',
      });

      const watcher = tmuxApi.watchSession('rg-test', 'vm-test-1', 'main', callback);
      watcher.start();

      await vi.advanceTimersByTimeAsync(20000);

      // Should be called only once (first poll establishes baseline)
      expect(callback).toHaveBeenCalledTimes(0);

      watcher.stop();
      vi.useRealTimers();
    });

    it('should stop watching when stop is called', async () => {
      vi.useFakeTimers();
      const callback = vi.fn();

      mockAzureClient.executeRunCommand.mockResolvedValue({
        exitCode: 0,
        stdout: 'SESSION_INFO:\n0:main:1\nPANE_CONTENT:\ncontent',
        stderr: '',
      });

      const watcher = tmuxApi.watchSession('rg-test', 'vm-test-1', 'main', callback);

      watcher.start();

      // Advance timer to trigger first poll
      await vi.advanceTimersByTimeAsync(10000);
      const callCountAfterStart = mockAzureClient.executeRunCommand.mock.calls.length;
      expect(callCountAfterStart).toBeGreaterThan(0);

      watcher.stop();

      // Advance timer again - should NOT trigger more polls
      await vi.advanceTimersByTimeAsync(20000);
      const callCountAfterStop = mockAzureClient.executeRunCommand.mock.calls.length;

      // No new calls should have been made after stop
      expect(callCountAfterStop).toBe(callCountAfterStart);

      vi.useRealTimers();
    });
  });
});
