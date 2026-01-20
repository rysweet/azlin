/**
 * Unit tests for AzureMonitorClient
 *
 * Testing strategy:
 * - Mock fetch API and TokenStorage
 * - Test successful metrics fetch
 * - Test error handling (401, 429, 500)
 * - Test retry logic for rate limiting
 * - Test input validation
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { AzureMonitorClient } from '../monitor-client';
import type { MetricsResponse } from '../monitor-client';

// Mock dependencies
vi.mock('../../auth/token-storage', () => ({
  TokenStorage: vi.fn().mockImplementation(() => ({
    getAccessToken: vi.fn().mockResolvedValue('mock-token'),
  })),
}));

vi.mock('../../utils/logger', () => ({
  createLogger: vi.fn(() => ({
    debug: vi.fn(),
    error: vi.fn(),
    warn: vi.fn(),
    info: vi.fn(),
  })),
}));

describe('AzureMonitorClient', () => {
  const mockSubscriptionId = 'test-subscription-123';
  const mockResourceId = '/subscriptions/test-subscription-123/resourceGroups/test-rg/providers/Microsoft.Compute/virtualMachines/test-vm';

  let client: AzureMonitorClient;
  let fetchMock: ReturnType<typeof vi.fn>;

  beforeEach(() => {
    client = new AzureMonitorClient(mockSubscriptionId);
    fetchMock = vi.fn();
    global.fetch = fetchMock;
  });

  describe('getVMMetrics', () => {
    it('should fetch metrics successfully', async () => {
      const mockResponse: MetricsResponse = {
        cost: 0,
        timespan: '2026-01-19T10:00:00Z/2026-01-19T10:15:00Z',
        interval: 'PT1M',
        value: [
          {
            id: `${mockResourceId}/providers/microsoft.insights/metrics/Percentage CPU`,
            type: 'Microsoft.Insights/metrics',
            name: {
              value: 'Percentage CPU',
              localizedValue: 'Percentage CPU',
            },
            unit: 'Percent',
            timeseries: [
              {
                data: [
                  { timeStamp: '2026-01-19T10:00:00Z', average: 75.5 },
                  { timeStamp: '2026-01-19T10:01:00Z', average: 78.2 },
                  { timeStamp: '2026-01-19T10:02:00Z', average: 82.1 },
                ],
              },
            ],
          },
        ],
        namespace: 'Microsoft.Compute/virtualMachines',
        resourceregion: 'eastus',
      };

      fetchMock.mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => mockResponse,
      });

      const result = await client.getVMMetrics(mockResourceId, {
        timespan: 'PT15M',
        interval: 'PT1M',
        metricnames: ['Percentage CPU'],
        aggregation: 'Average',
      });

      expect(result).toEqual(mockResponse);
      expect(result.value).toHaveLength(1);
      expect(result.value[0].name.value).toBe('Percentage CPU');
      expect(result.value[0].timeseries[0].data).toHaveLength(3);
    });

    it('should construct correct API URL', async () => {
      const mockResponse: MetricsResponse = {
        cost: 0,
        timespan: 'PT1H',
        interval: 'PT5M',
        value: [],
        namespace: 'Microsoft.Compute/virtualMachines',
        resourceregion: 'eastus',
      };

      fetchMock.mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => mockResponse,
      });

      await client.getVMMetrics(mockResourceId, {
        timespan: 'PT1H',
        interval: 'PT5M',
        metricnames: ['Percentage CPU', 'Available Memory Bytes'],
        aggregation: 'Average',
      });

      expect(fetchMock).toHaveBeenCalledTimes(1);
      const callUrl = fetchMock.mock.calls[0][0];
      expect(callUrl).toContain(mockResourceId);
      expect(callUrl).toContain('api-version=2024-02-01');
      expect(callUrl).toContain('timespan=PT1H');
      expect(callUrl).toContain('interval=PT5M');
      // URL encoding can use either %20 or + for spaces
      expect(callUrl).toMatch(/metricnames=Percentage(\+|%20)CPU%2CAvailable(\+|%20)Memory(\+|%20)Bytes/);
      expect(callUrl).toContain('aggregation=Average');
    });

    it('should include authorization header', async () => {
      const mockResponse: MetricsResponse = {
        cost: 0,
        timespan: 'PT15M',
        interval: 'PT1M',
        value: [],
        namespace: 'Microsoft.Compute/virtualMachines',
        resourceregion: 'eastus',
      };

      fetchMock.mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => mockResponse,
      });

      await client.getVMMetrics(mockResourceId, {
        timespan: 'PT15M',
        interval: 'PT1M',
        metricnames: ['Percentage CPU'],
      });

      expect(fetchMock).toHaveBeenCalledWith(
        expect.any(String),
        expect.objectContaining({
          headers: expect.objectContaining({
            'Authorization': 'Bearer mock-token',
          }),
        })
      );
    });

    it('should validate resourceId format', async () => {
      await expect(
        client.getVMMetrics('invalid-resource-id', {
          timespan: 'PT15M',
          interval: 'PT1M',
          metricnames: ['Percentage CPU'],
        })
      ).rejects.toThrow('Invalid resourceId: must start with /subscriptions/');
    });

    it('should validate required options', async () => {
      await expect(
        client.getVMMetrics(mockResourceId, {
          timespan: '',
          interval: 'PT1M',
          metricnames: ['Percentage CPU'],
        })
      ).rejects.toThrow('Invalid options: timespan, interval, and metricnames are required');

      await expect(
        client.getVMMetrics(mockResourceId, {
          timespan: 'PT15M',
          interval: '',
          metricnames: ['Percentage CPU'],
        })
      ).rejects.toThrow('Invalid options: timespan, interval, and metricnames are required');

      await expect(
        client.getVMMetrics(mockResourceId, {
          timespan: 'PT15M',
          interval: 'PT1M',
          metricnames: [],
        })
      ).rejects.toThrow('Invalid options: timespan, interval, and metricnames are required');
    });

    it('should handle 429 rate limit with retry', async () => {
      // First two calls return 429, third succeeds
      fetchMock
        .mockResolvedValueOnce({
          ok: false,
          status: 429,
          headers: new Map([['Retry-After', '1']]),
        })
        .mockResolvedValueOnce({
          ok: false,
          status: 429,
          headers: new Map([['Retry-After', '1']]),
        })
        .mockResolvedValueOnce({
          ok: true,
          status: 200,
          json: async () => ({
            cost: 0,
            timespan: 'PT15M',
            interval: 'PT1M',
            value: [],
            namespace: 'Microsoft.Compute/virtualMachines',
            resourceregion: 'eastus',
          }),
        });

      const result = await client.getVMMetrics(mockResourceId, {
        timespan: 'PT15M',
        interval: 'PT1M',
        metricnames: ['Percentage CPU'],
      });

      expect(fetchMock).toHaveBeenCalledTimes(3);
      expect(result.value).toEqual([]);
    });

    it('should fail after max retries on 429', async () => {
      fetchMock.mockResolvedValue({
        ok: false,
        status: 429,
        headers: new Map([['Retry-After', '1']]),
      });

      await expect(
        client.getVMMetrics(mockResourceId, {
          timespan: 'PT15M',
          interval: 'PT1M',
          metricnames: ['Percentage CPU'],
        })
      ).rejects.toThrow('Azure Monitor API rate limit exceeded after 3 retries');

      expect(fetchMock).toHaveBeenCalledTimes(4); // Initial + 3 retries
    });

    it('should handle 401 authentication error', async () => {
      fetchMock.mockResolvedValue({
        ok: false,
        status: 401,
        statusText: 'Unauthorized',
        text: async () => JSON.stringify({ error: { message: 'Invalid token' } }),
      });

      await expect(
        client.getVMMetrics(mockResourceId, {
          timespan: 'PT15M',
          interval: 'PT1M',
          metricnames: ['Percentage CPU'],
        })
      ).rejects.toThrow('Azure Monitor API error: Invalid token');
    });

    it('should handle 500 server error', async () => {
      fetchMock.mockResolvedValue({
        ok: false,
        status: 500,
        statusText: 'Internal Server Error',
        text: async () => JSON.stringify({ error: { message: 'Server error' } }),
      });

      await expect(
        client.getVMMetrics(mockResourceId, {
          timespan: 'PT15M',
          interval: 'PT1M',
          metricnames: ['Percentage CPU'],
        })
      ).rejects.toThrow('Azure Monitor API error: Server error');
    });

    it('should handle invalid response structure', async () => {
      fetchMock.mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ invalid: 'structure' }),
      });

      await expect(
        client.getVMMetrics(mockResourceId, {
          timespan: 'PT15M',
          interval: 'PT1M',
          metricnames: ['Percentage CPU'],
        })
      ).rejects.toThrow('Azure Monitor API returned unexpected response format - missing value array');
    });

    it('should fetch multiple metrics in single request', async () => {
      const mockResponse: MetricsResponse = {
        cost: 0,
        timespan: 'PT15M',
        interval: 'PT1M',
        value: [
          {
            id: `${mockResourceId}/providers/microsoft.insights/metrics/Percentage CPU`,
            type: 'Microsoft.Insights/metrics',
            name: { value: 'Percentage CPU', localizedValue: 'Percentage CPU' },
            unit: 'Percent',
            timeseries: [{ data: [{ timeStamp: '2026-01-19T10:00:00Z', average: 75.5 }] }],
          },
          {
            id: `${mockResourceId}/providers/microsoft.insights/metrics/Available Memory Bytes`,
            type: 'Microsoft.Insights/metrics',
            name: { value: 'Available Memory Bytes', localizedValue: 'Available Memory Bytes' },
            unit: 'Bytes',
            timeseries: [{ data: [{ timeStamp: '2026-01-19T10:00:00Z', average: 2000000000 }] }],
          },
        ],
        namespace: 'Microsoft.Compute/virtualMachines',
        resourceregion: 'eastus',
      };

      fetchMock.mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => mockResponse,
      });

      const result = await client.getVMMetrics(mockResourceId, {
        timespan: 'PT15M',
        interval: 'PT1M',
        metricnames: ['Percentage CPU', 'Available Memory Bytes'],
      });

      expect(result.value).toHaveLength(2);
      expect(result.value[0].name.value).toBe('Percentage CPU');
      expect(result.value[1].name.value).toBe('Available Memory Bytes');
    });
  });
});
