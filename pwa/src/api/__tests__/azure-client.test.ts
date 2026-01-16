/**
 * Unit Tests for Azure Client (60% of testing pyramid)
 *
 * Tests the Azure REST API client with mocked dependencies.
 * These tests WILL FAIL until azure-client.ts is implemented.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { AzureClient } from '../azure-client';
import { TokenStorage } from '../../auth/token-storage';

// Mock TokenStorage
vi.mock('../../auth/token-storage', () => ({
  TokenStorage: vi.fn().mockImplementation(() => ({
    getAccessToken: vi.fn().mockResolvedValue('mock_access_token'),
  })),
}));

describe('AzureClient', () => {
  let client: AzureClient;

  beforeEach(() => {
    client = new AzureClient('sub-123');
  });

  describe('constructor', () => {
    it('should initialize with subscription ID', () => {
      expect(client).toBeDefined();
      expect(client.subscriptionId).toBe('sub-123');
    });

    it('should initialize TokenStorage', () => {
      expect(TokenStorage).toHaveBeenCalled();
    });
  });

  describe('request', () => {
    it('should make authenticated GET request', async () => {
      const result = await client.get('/test/path');

      expect(result).toBeDefined();
      // Will fail until implemented
    });

    it('should include Bearer token in headers', async () => {
      const mockFetch = vi.spyOn(global, 'fetch').mockResolvedValue({
        ok: true,
        json: async () => ({ data: 'test' }),
      } as Response);

      await client.get('/test/path');

      expect(mockFetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          headers: expect.objectContaining({
            'Authorization': 'Bearer mock_access_token',
          }),
        })
      );
    });

    it('should include api-version parameter', async () => {
      const mockFetch = vi.spyOn(global, 'fetch').mockResolvedValue({
        ok: true,
        json: async () => ({ data: 'test' }),
      } as Response);

      await client.get('/test/path');

      const callUrl = mockFetch.mock.calls[0][0] as string;
      expect(callUrl).toContain('api-version=2023-03-01');
    });

    it('should handle POST requests with data', async () => {
      const testData = { key: 'value' };
      const mockFetch = vi.spyOn(global, 'fetch').mockResolvedValue({
        ok: true,
        json: async () => ({ success: true }),
      } as Response);

      await client.post('/test/path', testData);

      expect(mockFetch).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          method: 'POST',
          body: JSON.stringify(testData),
        })
      );
    });

    it('should handle network errors', async () => {
      vi.spyOn(global, 'fetch').mockRejectedValue(new Error('Network error'));

      await expect(client.get('/test/path')).rejects.toThrow('Network error');
    });

    it('should handle 401 unauthorized', async () => {
      vi.spyOn(global, 'fetch').mockResolvedValue({
        ok: false,
        status: 401,
        statusText: 'Unauthorized',
      } as Response);

      await expect(client.get('/test/path')).rejects.toThrow();
    });

    it('should handle 404 not found', async () => {
      vi.spyOn(global, 'fetch').mockResolvedValue({
        ok: false,
        status: 404,
        statusText: 'Not Found',
      } as Response);

      await expect(client.get('/test/path')).rejects.toThrow();
    });

    it('should retry on 429 rate limit', async () => {
      const mockFetch = vi.spyOn(global, 'fetch')
        .mockResolvedValueOnce({
          ok: false,
          status: 429,
          headers: new Headers({ 'Retry-After': '1' }),
        } as Response)
        .mockResolvedValueOnce({
          ok: true,
          json: async () => ({ data: 'success' }),
        } as Response);

      const result = await client.get('/test/path');

      expect(mockFetch).toHaveBeenCalledTimes(2);
      expect(result).toEqual({ data: 'success' });
    });
  });

  describe('listVMs', () => {
    it('should list all VMs in subscription', async () => {
      const vms = await client.listVMs();

      expect(vms).toBeInstanceOf(Array);
      expect(vms.length).toBeGreaterThan(0);
      // Will fail until implemented
    });

    it('should filter VMs by resource group', async () => {
      const vms = await client.listVMs('rg-test');

      expect(vms).toBeInstanceOf(Array);
      // Should only return VMs from rg-test
    });

    it('should filter VMs by azlin-managed tag', async () => {
      const vms = await client.listVMs();
      const azlinVMs = vms.filter(vm => vm.tags?.['azlin-managed'] === 'true');

      expect(azlinVMs.length).toBe(vms.length);
    });

    it('should parse VM power state correctly', async () => {
      const vms = await client.listVMs();
      const runningVM = vms.find(vm => vm.name === 'vm-test-1');

      expect(runningVM?.powerState).toBe('running');
    });

    it('should parse VM private IP correctly', async () => {
      const vms = await client.listVMs();
      const vm = vms.find(vm => vm.name === 'vm-test-1');

      expect(vm?.privateIP).toBe('10.0.0.4');
    });

    it('should parse VM size correctly', async () => {
      const vms = await client.listVMs();
      const vm = vms.find(vm => vm.name === 'vm-test-1');

      expect(vm?.size).toBe('Standard_B2s');
    });

    it('should handle empty VM list', async () => {
      vi.spyOn(global, 'fetch').mockResolvedValue({
        ok: true,
        json: async () => ({ value: [] }),
      } as Response);

      const vms = await client.listVMs();

      expect(vms).toEqual([]);
    });
  });

  describe('startVM', () => {
    it('should start a VM', async () => {
      const result = await client.startVM('rg-test', 'vm-test-1');

      expect(result).toBeDefined();
      // Will fail until implemented
    });

    it('should return 202 Accepted status', async () => {
      const mockFetch = vi.spyOn(global, 'fetch').mockResolvedValue({
        ok: true,
        status: 202,
        json: async () => ({}),
      } as Response);

      await client.startVM('rg-test', 'vm-test-1');

      expect(mockFetch).toHaveBeenCalled();
    });

    it('should handle VM not found error', async () => {
      vi.spyOn(global, 'fetch').mockResolvedValue({
        ok: false,
        status: 404,
        statusText: 'Not Found',
      } as Response);

      await expect(client.startVM('rg-test', 'nonexistent')).rejects.toThrow();
    });
  });

  describe('stopVM', () => {
    it('should stop VM (power off)', async () => {
      const result = await client.stopVM('rg-test', 'vm-test-1', false);

      expect(result).toBeDefined();
      // Will fail until implemented
    });

    it('should deallocate VM when deallocate=true', async () => {
      const mockFetch = vi.spyOn(global, 'fetch').mockResolvedValue({
        ok: true,
        status: 202,
        json: async () => ({}),
      } as Response);

      await client.stopVM('rg-test', 'vm-test-1', true);

      const callUrl = mockFetch.mock.calls[0][0] as string;
      expect(callUrl).toContain('/deallocate');
    });

    it('should power off VM when deallocate=false', async () => {
      const mockFetch = vi.spyOn(global, 'fetch').mockResolvedValue({
        ok: true,
        status: 202,
        json: async () => ({}),
      } as Response);

      await client.stopVM('rg-test', 'vm-test-1', false);

      const callUrl = mockFetch.mock.calls[0][0] as string;
      expect(callUrl).toContain('/powerOff');
    });
  });

  describe('executeRunCommand', () => {
    it('should execute shell script on VM', async () => {
      const script = 'echo "Hello World"';
      const result = await client.executeRunCommand('rg-test', 'vm-test-1', script);

      expect(result).toBeDefined();
      expect(result.exitCode).toBeDefined();
      expect(result.stdout).toBeDefined();
      // Will fail until implemented
    });

    it('should parse stdout correctly', async () => {
      const result = await client.executeRunCommand('rg-test', 'vm-test-1', 'ls -la');

      expect(result.stdout).toBeTruthy();
    });

    it('should parse stderr correctly', async () => {
      const result = await client.executeRunCommand('rg-test', 'vm-test-1', 'ls -la');

      expect(result.stderr).toBeDefined();
    });

    it('should handle command timeout', async () => {
      vi.spyOn(global, 'fetch').mockImplementation(() =>
        new Promise((resolve) => {
          setTimeout(() => resolve({
            ok: false,
            status: 408,
            statusText: 'Request Timeout',
          } as Response), 100);
        })
      );

      await expect(
        client.executeRunCommand('rg-test', 'vm-test-1', 'sleep 100')
      ).rejects.toThrow();
    });
  });
});
