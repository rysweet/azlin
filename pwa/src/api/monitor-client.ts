/**
 * Azure Monitor API Client for VM Metrics
 *
 * Provides interface to Azure Monitor REST API:
 * - Fetch VM performance metrics (CPU, Memory, Network, Disk)
 * - Support for time-series data with custom time ranges
 * - Automatic token refresh via TokenStorage
 * - Retry logic for rate limiting (429)
 *
 * Philosophy:
 * - Single responsibility: Azure Monitor API communication
 * - Self-contained with clear public API
 * - Zero-BS: No stubs, every method works
 */

import { TokenStorage } from '../auth/token-storage';
import { createLogger } from '../utils/logger';

const logger = createLogger('[MonitorClient]');
const AZURE_BASE_URL = 'https://management.azure.com';
const MONITOR_API_VERSION = '2024-02-01'; // Azure Monitor API version

/**
 * Options for querying metrics from Azure Monitor
 */
export interface MetricsQueryOptions {
  /**
   * ISO 8601 duration string
   * Examples: 'PT15M' (15 minutes), 'PT1H' (1 hour), 'PT6H' (6 hours), 'P1D' (1 day)
   */
  timespan: string;

  /**
   * Time granularity for data points
   * Examples: 'PT1M' (1 minute), 'PT5M' (5 minutes), 'PT15M' (15 minutes)
   */
  interval: string;

  /**
   * Metrics to fetch from Azure Monitor
   * Examples: ['Percentage CPU', 'Available Memory Bytes', 'Network In Total']
   */
  metricnames: string[];

  /**
   * Aggregation type for metric values
   * Default: 'Average'
   */
  aggregation?: 'Average' | 'Maximum' | 'Minimum' | 'Total' | 'Count';
}

/**
 * Single data point in a time-series metric
 */
export interface DataPoint {
  timeStamp: string;
  average?: number;
  maximum?: number;
  minimum?: number;
  total?: number;
  count?: number;
}

/**
 * Time-series data for a metric
 */
export interface Timeseries {
  data: DataPoint[];
  metadatavalues?: Array<{ name: { value: string }; value: string }>;
}

/**
 * Individual metric response from Azure Monitor
 */
export interface Metric {
  id: string;
  type: string;
  name: {
    value: string;
    localizedValue: string;
  };
  unit: string;
  timeseries: Timeseries[];
  displayDescription?: string;
}

/**
 * Complete metrics response from Azure Monitor API
 */
export interface MetricsResponse {
  cost: number;
  timespan: string;
  interval: string;
  value: Metric[];
  namespace: string;
  resourceregion: string;
}

/**
 * Azure Monitor API Client
 *
 * Example Usage:
 * ```typescript
 * const client = new AzureMonitorClient(subscriptionId);
 * const metrics = await client.getVMMetrics(vmResourceId, {
 *   timespan: 'PT15M',
 *   interval: 'PT1M',
 *   metricnames: ['Percentage CPU', 'Available Memory Bytes'],
 *   aggregation: 'Average'
 * });
 * ```
 */
export class AzureMonitorClient {
  private tokenStorage: TokenStorage;

  constructor(_subscriptionId: string) {
    // subscriptionId will be used in future API calls
    this.tokenStorage = new TokenStorage();
  }

  /**
   * Fetch VM metrics from Azure Monitor
   *
   * @param resourceId - Full Azure resource ID of the VM
   *   Format: /subscriptions/{subscriptionId}/resourceGroups/{resourceGroup}/providers/Microsoft.Compute/virtualMachines/{vmName}
   * @param options - Query options (timespan, interval, metrics, aggregation)
   * @returns Metrics response with time-series data
   *
   * @throws Error if API request fails or returns invalid data
   *
   * Example:
   * ```typescript
   * const metrics = await client.getVMMetrics(
   *   '/subscriptions/abc123/resourceGroups/my-rg/providers/Microsoft.Compute/virtualMachines/my-vm',
   *   {
   *     timespan: 'PT1H',
   *     interval: 'PT1M',
   *     metricnames: ['Percentage CPU'],
   *     aggregation: 'Average'
   *   }
   * );
   * ```
   */
  async getVMMetrics(
    resourceId: string,
    options: MetricsQueryOptions
  ): Promise<MetricsResponse> {
    logger.debug('getVMMetrics called', { resourceId, options });

    // Validate inputs
    if (!resourceId || !resourceId.startsWith('/subscriptions/')) {
      throw new Error('Invalid resourceId: must start with /subscriptions/');
    }

    if (!options.timespan || !options.interval || !options.metricnames?.length) {
      throw new Error('Invalid options: timespan, interval, and metricnames are required');
    }

    // Build URL
    const path = `${resourceId}/providers/microsoft.insights/metrics`;
    const url = new URL(`${AZURE_BASE_URL}${path}`);
    url.searchParams.set('api-version', MONITOR_API_VERSION);
    url.searchParams.set('timespan', options.timespan);
    url.searchParams.set('interval', options.interval);
    url.searchParams.set('metricnames', options.metricnames.join(','));
    url.searchParams.set('aggregation', options.aggregation || 'Average');

    logger.debug('Fetching metrics from Azure Monitor', { url: url.toString() });

    return this.request<MetricsResponse>(url.toString());
  }

  /**
   * Make authenticated request to Azure Monitor API with retry logic
   */
  private async request<T>(
    url: string,
    retryCount: number = 0
  ): Promise<T> {
    const MAX_RETRIES = 3;
    const token = await this.tokenStorage.getAccessToken();

    const response = await fetch(url, {
      method: 'GET',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
    });

    // Handle rate limiting with exponential backoff
    if (response.status === 429) {
      if (retryCount >= MAX_RETRIES) {
        throw new Error(
          `Azure Monitor API rate limit exceeded after ${MAX_RETRIES} retries. Status: ${response.status}`
        );
      }

      const retryAfter = response.headers.get('Retry-After');
      const delay = retryAfter ? parseInt(retryAfter) * 1000 : Math.pow(2, retryCount) * 1000;

      logger.debug(`Rate limited (429), retrying in ${delay / 1000}s... (attempt ${retryCount + 1}/${MAX_RETRIES})`);

      await new Promise(resolve => setTimeout(resolve, delay));
      return this.request<T>(url, retryCount + 1);
    }

    if (!response.ok) {
      // Read response body for error details
      let errorDetails = `${response.status} ${response.statusText}`;
      try {
        const responseText = await response.text();
        if (responseText) {
          const errorBody = JSON.parse(responseText);
          errorDetails = errorBody?.error?.message || JSON.stringify(errorBody, null, 2);
          logger.error('Azure Monitor API error response:', errorBody);
        }
      } catch (e) {
        // Failed to parse error, use status text
      }

      throw new Error(`Azure Monitor API error: ${errorDetails}`);
    }

    // Parse JSON response
    const data = await response.json();

    // Validate response structure
    if (!data || !Array.isArray(data.value)) {
      logger.error('Invalid response structure from Azure Monitor API:', data);
      throw new Error('Azure Monitor API returned unexpected response format - missing value array');
    }

    logger.debug('Azure Monitor API response:', {
      metricCount: data.value.length,
      timespan: data.timespan,
      interval: data.interval,
    });

    return data as T;
  }
}

export default AzureMonitorClient;
