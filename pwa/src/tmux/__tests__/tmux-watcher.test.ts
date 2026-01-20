/**
 * Integration Tests for Tmux Watcher Lifecycle
 *
 * Tests the complete watcher lifecycle including start, stop, and error handling.
 *
 * Philosophy:
 * - Test the contract, not implementation
 * - Test real integration between components
 * - Simulate real-world scenarios
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { TmuxApi, TmuxWatcher } from '../tmux-api';
import { AzureClient } from '../../api/azure-client';

// Mock AzureClient
vi.mock('../../api/azure-client');

describe('Tmux Watcher Lifecycle', () => {
  let tmuxApi: TmuxApi;
  let mockAzureClient: any;

  beforeEach(() => {
    // Create mock Azure client
    mockAzureClient = new AzureClient('test-subscription');
    tmuxApi = new TmuxApi(mockAzureClient);

    // Setup default mock implementation
    mockAzureClient.executeRunCommand = vi.fn().mockResolvedValue({
      exitCode: 0,
      stdout: 'SESSION_INFO:\n0:bash:1\nPANE_CONTENT:\ntest line 1\ntest line 2',
      stderr: '',
    });
  });

  afterEach(() => {
    vi.clearAllMocks();
    vi.clearAllTimers();
  });

  describe('Watcher Start/Stop', () => {
    it('should start watcher and call onChange callback when content changes', async () => {
      vi.useFakeTimers();

      const onChangeCallback = vi.fn();
      const onErrorCallback = vi.fn();

      // Mock different snapshots for each call
      let callCount = 0;
      mockAzureClient.executeRunCommand = vi.fn().mockImplementation(() => {
        callCount++;
        if (callCount === 1) {
          return Promise.resolve({
            exitCode: 0,
            stdout: 'SESSION_INFO:\n0:bash:1\nPANE_CONTENT:\nline 1',
            stderr: '',
          });
        } else {
          return Promise.resolve({
            exitCode: 0,
            stdout: 'SESSION_INFO:\n0:bash:1\nPANE_CONTENT:\nline 1\nline 2',
            stderr: '',
          });
        }
      });

      const watcher: TmuxWatcher = tmuxApi.watchSession(
        'test-rg',
        'test-vm',
        'test-session',
        onChangeCallback,
        1000, // 1 second interval
        onErrorCallback
      );

      watcher.start();

      // First check (establishes baseline)
      await vi.advanceTimersByTimeAsync(1000);
      expect(onChangeCallback).not.toHaveBeenCalled(); // No baseline yet

      // Second check (detects change)
      await vi.advanceTimersByTimeAsync(1000);
      expect(onChangeCallback).toHaveBeenCalledTimes(1);
      expect(onChangeCallback).toHaveBeenCalledWith({
        hasChanges: true,
        changedLines: expect.arrayContaining([
          expect.objectContaining({
            lineNumber: expect.any(Number),
            oldContent: expect.any(String),
            newContent: expect.any(String),
          }),
        ]),
      });

      expect(onErrorCallback).not.toHaveBeenCalled();

      watcher.stop();
      vi.useRealTimers();
    });

    it('should stop watcher and clear interval', async () => {
      vi.useFakeTimers();

      const onChangeCallback = vi.fn();

      const watcher: TmuxWatcher = tmuxApi.watchSession(
        'test-rg',
        'test-vm',
        'test-session',
        onChangeCallback,
        1000
      );

      watcher.start();

      // Advance once
      await vi.advanceTimersByTimeAsync(1000);
      const callsAfterFirstInterval = mockAzureClient.executeRunCommand.mock.calls.length;

      // Stop watcher
      watcher.stop();

      // Advance again - should NOT call executeRunCommand
      await vi.advanceTimersByTimeAsync(1000);
      const callsAfterStop = mockAzureClient.executeRunCommand.mock.calls.length;

      expect(callsAfterStop).toBe(callsAfterFirstInterval);

      vi.useRealTimers();
    });

    it('should not call onChange when content is unchanged', async () => {
      vi.useFakeTimers();

      const onChangeCallback = vi.fn();

      // Mock identical snapshots
      mockAzureClient.executeRunCommand = vi.fn().mockResolvedValue({
        exitCode: 0,
        stdout: 'SESSION_INFO:\n0:bash:1\nPANE_CONTENT:\nstatic content',
        stderr: '',
      });

      const watcher: TmuxWatcher = tmuxApi.watchSession(
        'test-rg',
        'test-vm',
        'test-session',
        onChangeCallback,
        1000
      );

      watcher.start();

      // First check (establishes baseline)
      await vi.advanceTimersByTimeAsync(1000);

      // Second check (no change)
      await vi.advanceTimersByTimeAsync(1000);

      // Third check (no change)
      await vi.advanceTimersByTimeAsync(1000);

      expect(onChangeCallback).not.toHaveBeenCalled();

      watcher.stop();
      vi.useRealTimers();
    });
  });

  describe('Error Handling', () => {
    it('should call onError callback when capture fails', async () => {
      vi.useFakeTimers();

      const onChangeCallback = vi.fn();
      const onErrorCallback = vi.fn();

      // Mock failure
      mockAzureClient.executeRunCommand = vi.fn().mockRejectedValue(
        new Error('Network timeout')
      );

      const watcher: TmuxWatcher = tmuxApi.watchSession(
        'test-rg',
        'test-vm',
        'test-session',
        onChangeCallback,
        1000,
        onErrorCallback
      );

      watcher.start();

      await vi.advanceTimersByTimeAsync(1000);

      expect(onErrorCallback).toHaveBeenCalledTimes(1);
      expect(onErrorCallback).toHaveBeenCalledWith(expect.any(Error));
      expect(onErrorCallback.mock.calls[0][0].message).toBe('Network timeout');

      watcher.stop();
      vi.useRealTimers();
    });

    it('should continue watching after error if not stopped', async () => {
      vi.useFakeTimers();

      const onChangeCallback = vi.fn();
      const onErrorCallback = vi.fn();

      let callCount = 0;
      mockAzureClient.executeRunCommand = vi.fn().mockImplementation(() => {
        callCount++;
        if (callCount === 1) {
          return Promise.reject(new Error('Temporary failure'));
        } else {
          return Promise.resolve({
            exitCode: 0,
            stdout: 'SESSION_INFO:\n0:bash:1\nPANE_CONTENT:\nrecovered',
            stderr: '',
          });
        }
      });

      const watcher: TmuxWatcher = tmuxApi.watchSession(
        'test-rg',
        'test-vm',
        'test-session',
        onChangeCallback,
        1000,
        onErrorCallback
      );

      watcher.start();

      // First check - error
      await vi.advanceTimersByTimeAsync(1000);
      expect(onErrorCallback).toHaveBeenCalledTimes(1);

      // Second check - success
      await vi.advanceTimersByTimeAsync(1000);
      expect(mockAzureClient.executeRunCommand).toHaveBeenCalledTimes(2);

      watcher.stop();
      vi.useRealTimers();
    });
  });

  describe('Change Detection', () => {
    it('should detect new lines (additions)', async () => {
      vi.useFakeTimers();

      const onChangeCallback = vi.fn();

      let callCount = 0;
      mockAzureClient.executeRunCommand = vi.fn().mockImplementation(() => {
        callCount++;
        if (callCount === 1) {
          return Promise.resolve({
            exitCode: 0,
            stdout: 'SESSION_INFO:\n0:bash:1\nPANE_CONTENT:\nline 1',
            stderr: '',
          });
        } else {
          return Promise.resolve({
            exitCode: 0,
            stdout: 'SESSION_INFO:\n0:bash:1\nPANE_CONTENT:\nline 1\nline 2 (new)',
            stderr: '',
          });
        }
      });

      const watcher: TmuxWatcher = tmuxApi.watchSession(
        'test-rg',
        'test-vm',
        'test-session',
        onChangeCallback,
        1000
      );

      watcher.start();

      // Establish baseline
      await vi.advanceTimersByTimeAsync(1000);

      // Detect change
      await vi.advanceTimersByTimeAsync(1000);

      expect(onChangeCallback).toHaveBeenCalledTimes(1);
      const diff = onChangeCallback.mock.calls[0][0];
      expect(diff.hasChanges).toBe(true);
      expect(diff.changedLines.length).toBeGreaterThan(0);

      watcher.stop();
      vi.useRealTimers();
    });

    it('should detect modified lines (changes)', async () => {
      vi.useFakeTimers();

      const onChangeCallback = vi.fn();

      let callCount = 0;
      mockAzureClient.executeRunCommand = vi.fn().mockImplementation(() => {
        callCount++;
        if (callCount === 1) {
          return Promise.resolve({
            exitCode: 0,
            stdout: 'SESSION_INFO:\n0:bash:1\nPANE_CONTENT:\noriginal line',
            stderr: '',
          });
        } else {
          return Promise.resolve({
            exitCode: 0,
            stdout: 'SESSION_INFO:\n0:bash:1\nPANE_CONTENT:\nmodified line',
            stderr: '',
          });
        }
      });

      const watcher: TmuxWatcher = tmuxApi.watchSession(
        'test-rg',
        'test-vm',
        'test-session',
        onChangeCallback,
        1000
      );

      watcher.start();

      // Establish baseline
      await vi.advanceTimersByTimeAsync(1000);

      // Detect change
      await vi.advanceTimersByTimeAsync(1000);

      expect(onChangeCallback).toHaveBeenCalledTimes(1);
      const diff = onChangeCallback.mock.calls[0][0];
      expect(diff.hasChanges).toBe(true);
      expect(diff.changedLines[0].oldContent).toBe('original line');
      expect(diff.changedLines[0].newContent).toBe('modified line');

      watcher.stop();
      vi.useRealTimers();
    });
  });

  describe('Custom Intervals', () => {
    it('should respect 5-second interval', async () => {
      vi.useFakeTimers();

      const onChangeCallback = vi.fn();

      const watcher: TmuxWatcher = tmuxApi.watchSession(
        'test-rg',
        'test-vm',
        'test-session',
        onChangeCallback,
        5000 // 5 seconds
      );

      watcher.start();

      await vi.advanceTimersByTimeAsync(4999);
      expect(mockAzureClient.executeRunCommand).not.toHaveBeenCalled();

      await vi.advanceTimersByTimeAsync(1);
      expect(mockAzureClient.executeRunCommand).toHaveBeenCalledTimes(1);

      watcher.stop();
      vi.useRealTimers();
    });

    it('should respect 60-second interval', async () => {
      vi.useFakeTimers();

      const onChangeCallback = vi.fn();

      const watcher: TmuxWatcher = tmuxApi.watchSession(
        'test-rg',
        'test-vm',
        'test-session',
        onChangeCallback,
        60000 // 60 seconds
      );

      watcher.start();

      await vi.advanceTimersByTimeAsync(59999);
      expect(mockAzureClient.executeRunCommand).not.toHaveBeenCalled();

      await vi.advanceTimersByTimeAsync(1);
      expect(mockAzureClient.executeRunCommand).toHaveBeenCalledTimes(1);

      watcher.stop();
      vi.useRealTimers();
    });
  });
});
