/**
 * Azure REST API Client for Azlin Mobile PWA
 *
 * Provides interface to Azure Management APIs:
 * - VM Management (list, start, stop, deallocate)
 * - Run Command API (execute scripts on VMs)
 * - Automatic token refresh via TokenStorage
 * - Retry logic for rate limiting (429)
 *
 * Philosophy:
 * - Single responsibility: Azure API communication
 * - Self-contained with clear public API
 * - Zero-BS: No stubs, every method works
 */

import { TokenStorage } from '../auth/token-storage';

const AZURE_BASE_URL = 'https://management.azure.com';
const API_VERSION = '2024-11-01'; // Updated to match az CLI version

export interface VMInfo {
  id: string;
  name: string;
  resourceGroup: string;
  location: string;
  size: string;
  powerState: string;
  privateIP?: string;
  osType: string;
  tags?: Record<string, string>;
}

export interface RunCommandResult {
  exitCode: number;
  stdout: string;
  stderr: string;
  executionTime?: string;
}

export class AzureClient {
  public readonly subscriptionId: string;
  private tokenStorage: TokenStorage;

  constructor(subscriptionId: string) {
    this.subscriptionId = subscriptionId;
    this.tokenStorage = new TokenStorage();
  }

  /**
   * Make authenticated request to Azure Management API
   */
  private async request<T>(
    method: string,
    path: string,
    data?: unknown,
    retryCount: number = 0
  ): Promise<T> {
    const MAX_RETRIES = 3;
    const token = await this.tokenStorage.getAccessToken();

    const url = new URL(`${AZURE_BASE_URL}${path}`);
    url.searchParams.set('api-version', API_VERSION);

    const options: RequestInit = {
      method,
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
    };

    if (data) {
      options.body = JSON.stringify(data);
    }

    const response = await fetch(url.toString(), options);

    // Handle rate limiting with retry (max 3 retries)
    if (response.status === 429) {
      if (retryCount >= MAX_RETRIES) {
        throw new Error(
          `Azure API rate limit exceeded after ${MAX_RETRIES} retries. Status: ${response.status}`
        );
      }

      const retryAfter = response.headers.get('Retry-After');
      const delay = retryAfter ? parseInt(retryAfter) * 1000 : 1000;

      await new Promise(resolve => setTimeout(resolve, delay));
      return this.request<T>(method, path, data, retryCount + 1);
    }

    if (!response.ok) {
      // Get detailed error response from Azure
      let errorDetails = `${response.status} ${response.statusText}`;
      try {
        const errorBody = await response.json();
        errorDetails = JSON.stringify(errorBody, null, 2);
        console.error('🏴‍☠️ Azure API error response:', errorBody);
      } catch (e) {
        // Can't parse error body
      }

      throw new Error(`Azure API error: ${errorDetails}`);
    }

    return response.json();
  }

  /**
   * Convenience methods for HTTP verbs
   */
  async get<T>(path: string): Promise<T> {
    return this.request<T>('GET', path);
  }

  async post<T>(path: string, data?: unknown): Promise<T> {
    return this.request<T>('POST', path, data);
  }

  async put<T>(path: string, data: unknown): Promise<T> {
    return this.request<T>('PUT', path, data);
  }

  async delete<T>(path: string): Promise<T> {
    return this.request<T>('DELETE', path);
  }

  /**
   * List all VMs in subscription, optionally filtered by resource group
   * Uses $expand=instanceView to get power state information
   */
  async listVMs(resourceGroup?: string): Promise<VMInfo[]> {
    console.log('🏴‍☠️ AzureClient.listVMs called', { subscriptionId: this.subscriptionId, resourceGroup });

    const basePath = resourceGroup
      ? `/subscriptions/${this.subscriptionId}/resourceGroups/${resourceGroup}/providers/Microsoft.Compute/virtualMachines`
      : `/subscriptions/${this.subscriptionId}/providers/Microsoft.Compute/virtualMachines`;

    console.log('🏴‍☠️ Calling Azure API:', basePath);

    try {
      // First get the list of VMs
      const response = await this.get<{ value: Array<unknown> }>(basePath);
      console.log('🏴‍☠️ Azure API response:', { count: response.value.length });

      // Then fetch instance view for each VM to get power state
      const vmsWithStatus = await Promise.all(
        response.value.map(async (vm: any) => {
          try {
            // Get instance view for this specific VM
            const instanceViewPath = `${vm.id}/instanceView`;
            const instanceView = await this.get<any>(instanceViewPath);
            // Merge instance view into VM data
            return { ...vm, properties: { ...vm.properties, instanceView } };
          } catch (e) {
            console.warn(`🏴‍☠️ Failed to get instance view for ${vm.name}:`, e);
            return vm;
          }
        })
      );

      const vms = vmsWithStatus.map((vm: any) => this.parseVM(vm));
      console.log('🏴‍☠️ Parsed VMs:', vms.length, vms);

      return vms;
    } catch (error) {
      console.error('🏴‍☠️ Failed to list VMs:', error);
      throw error;
    }
  }

  /**
   * Parse Azure VM response to VMInfo
   */
  private parseVM(raw: any): VMInfo {
    // Extract resource group from ID
    const idParts = raw.id.split('/');
    const resourceGroup = idParts[4];

    // Extract power state from instanceView statuses
    let powerState = 'unknown';
    if (raw.properties?.instanceView?.statuses) {
      const powerStatus = raw.properties.instanceView.statuses.find(
        (s: any) => s.code?.startsWith('PowerState/')
      );
      if (powerStatus) {
        powerState = powerStatus.code.replace('PowerState/', '');
      }
    }

    // Extract private IP from network interfaces
    let privateIP: string | undefined;
    if (raw.properties?.networkProfile?.networkInterfaces?.[0]?.properties?.privateIPAddress) {
      privateIP = raw.properties.networkProfile.networkInterfaces[0].properties.privateIPAddress;
    }

    return {
      id: raw.id,
      name: raw.name,
      resourceGroup,
      location: raw.location,
      size: raw.properties.hardwareProfile.vmSize,
      powerState,
      privateIP,
      osType: raw.properties.storageProfile.osDisk.osType,
      tags: raw.tags,
    };
  }

  /**
   * Start a VM
   */
  async startVM(resourceGroup: string, vmName: string): Promise<void> {
    const path = `/subscriptions/${this.subscriptionId}/resourceGroups/${resourceGroup}/providers/Microsoft.Compute/virtualMachines/${vmName}/start`;
    await this.post(path);
  }

  /**
   * Stop a VM (power off or deallocate)
   */
  async stopVM(
    resourceGroup: string,
    vmName: string,
    deallocate: boolean = true
  ): Promise<void> {
    const action = deallocate ? 'deallocate' : 'powerOff';
    const path = `/subscriptions/${this.subscriptionId}/resourceGroups/${resourceGroup}/providers/Microsoft.Compute/virtualMachines/${vmName}/${action}`;
    await this.post(path);
  }

  /**
   * Execute shell script on VM via Run Command API
   * Timeout: 90 seconds (Azure constraint)
   */
  async executeRunCommand(
    resourceGroup: string,
    vmName: string,
    script: string
  ): Promise<RunCommandResult> {
    const path = `/subscriptions/${this.subscriptionId}/resourceGroups/${resourceGroup}/providers/Microsoft.Compute/virtualMachines/${vmName}/runCommand`;

    const body = {
      commandId: 'RunShellScript',
      script: [script],
      parameters: [],
    };

    const response = await this.post<any>(path, body);
    return this.parseRunCommandResult(response);
  }

  /**
   * Parse Run Command API response
   */
  private parseRunCommandResult(response: any): RunCommandResult {
    const value = response.value || [];

    return {
      exitCode: value[0]?.code === 'ComponentStatus/StdOut/succeeded' ? 0 : 1,
      stdout: value[0]?.message || '',
      stderr: value[1]?.message || '',
      executionTime: value[0]?.displayStatus,
    };
  }
}

export default AzureClient;
