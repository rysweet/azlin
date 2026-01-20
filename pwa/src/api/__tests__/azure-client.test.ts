/**
 * Unit Tests for Azure Client (60% of testing pyramid)
 *
 * Tests the Azure REST API client with MSW mocked responses.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { AzureClient } from '../azure-client';
import { TokenStorage } from '../../auth/token-storage';

describe('AzureClient', () => {
  let client: AzureClient;
  let tokenStorage: TokenStorage;

  beforeEach(async () => {
    // Initialize real TokenStorage with mock token
    tokenStorage = new TokenStorage();
    await tokenStorage.saveTokens(
      'mock_access_token',
      'mock_refresh_token',
      Date.now() + 3600000
    );

    client = new AzureClient('sub-123');
  });

  afterEach(async () => {
    await tokenStorage.clearTokens();
    vi.clearAllMocks();
  });

  describe('constructor', () => {
    it('should initialize with subscription ID', () => {
      expect(client).toBeDefined();
      expect(client.subscriptionId).toBe('sub-123');
    });
  });

  // Request tests removed - covered by integration tests with MSW

  describe('listVMs', () => {
    it('should list all VMs in subscription', async () => {
      const vms = await client.listVMs();

      expect(vms).toBeInstanceOf(Array);
      expect(vms.length).toBeGreaterThan(0);
    });

    it('should parse VM properties correctly', async () => {
      const vms = await client.listVMs();
      const vm = vms.find(vm => vm.name === 'vm-test-1');

      expect(vm).toBeDefined();
      expect(vm?.powerState).toBe('running');
      expect(vm?.privateIP).toBe('10.0.0.4');
      expect(vm?.size).toBe('Standard_B2s');
      expect(vm?.tags?.['azlin-managed']).toBe('true');
    });
  });

  describe('startVM', () => {
    it('should start a VM', async () => {
      await expect(
        client.startVM('rg-test', 'vm-test-1')
      ).resolves.not.toThrow();
    });
  });

  describe('stopVM', () => {
    it('should stop VM (power off)', async () => {
      await expect(
        client.stopVM('rg-test', 'vm-test-1', false)
      ).resolves.not.toThrow();
    });

    it('should deallocate VM', async () => {
      await expect(
        client.stopVM('rg-test', 'vm-test-1', true)
      ).resolves.not.toThrow();
    });
  });

  describe('executeRunCommand', () => {
    it('should execute shell script on VM', async () => {
      const script = 'echo "Hello World"';
      const result = await client.executeRunCommand('rg-test', 'vm-test-1', script);

      expect(result).toBeDefined();
      expect(result.exitCode).toBeDefined();
      expect(result.stdout).toBeDefined();
    });
  });
});
