/**
 * Azure REST API Client for Azlin Mobile PWA
 *
 * Provides interface to Azure Management APIs:
 * - VM Management (list, start, stop, deallocate)
 * - Run Command API (execute scripts on VMs)
 * - Automatic token refresh via TokenStorage
 * - Retry logic for rate limiting (429) and VM busy (409)
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

export interface PollingProgress {
  attempt: number;
  maxAttempts: number;
  message: string;
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

    // Handle 409 Conflict with retry and exponential backoff (VM busy)
    if (response.status === 409) {
      if (retryCount >= MAX_RETRIES) {
        throw new Error(
          `VM is busy - operation failed after ${MAX_RETRIES} retries. Another operation may still be in progress.`
        );
      }

      // Exponential backoff: 2s, 4s, 8s
      const delay = Math.pow(2, retryCount + 1) * 1000;
      console.log(`🏴‍☠️ VM busy (409 Conflict), trying again in ${delay / 1000}s... (attempt ${retryCount + 1}/${MAX_RETRIES})`);

      await new Promise(resolve => setTimeout(resolve, delay));
      return this.request<T>(method, path, data, retryCount + 1);
    }

    if (!response.ok) {
      // Read the response body as text first (can only read once)
      let responseText = '';
      try {
        responseText = await response.text();
      } catch (e) {
        // Could not read response body
      }

      // Try to parse as JSON for detailed error info
      let errorDetails = `${response.status} ${response.statusText}`;
      if (responseText) {
        try {
          const errorBody = JSON.parse(responseText);
          errorDetails = errorBody?.error?.message || JSON.stringify(errorBody, null, 2);
          console.error('🏴‍☠️ Azure API error response:', errorBody);
        } catch (e) {
          // Not JSON, use raw text
          errorDetails = responseText || errorDetails;
        }
      }

      throw new Error(`Azure API error: ${errorDetails}`);
    }

    // Handle empty response body (e.g., 202 Accepted with no content)
    const contentType = response.headers.get('content-type');
    if (!contentType || !contentType.includes('application/json')) {
      return {} as T;
    }

    const text = await response.text();
    if (!text || text.trim() === '') {
      return {} as T;
    }

    return JSON.parse(text);
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
   *
   * Azure Run Command returns 202 Accepted with a location header for async polling.
   * We must poll that URL until the operation completes (up to 90 seconds).
   *
   * @param onProgress - Optional callback to report polling progress to UI
   */
  async executeRunCommand(
    resourceGroup: string,
    vmName: string,
    script: string,
    onProgress?: (progress: PollingProgress) => void
  ): Promise<RunCommandResult> {
    const token = await this.tokenStorage.getAccessToken();
    const path = `/subscriptions/${this.subscriptionId}/resourceGroups/${resourceGroup}/providers/Microsoft.Compute/virtualMachines/${vmName}/runCommand`;
    const url = new URL(`${AZURE_BASE_URL}${path}`);
    url.searchParams.set('api-version', API_VERSION);

    const body = {
      commandId: 'RunShellScript',
      script: [script],
      parameters: [],
    };

    console.log('🏴‍☠️ Executing Run Command on', vmName);

    // Initial POST request
    const response = await fetch(url.toString(), {
      method: 'POST',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(body),
    });

    // Handle 409 Conflict (VM busy)
    if (response.status === 409) {
      throw new Error('VM is busy - another command may be running. Try again in a moment.');
    }

    if (!response.ok && response.status !== 202) {
      const errorText = await response.text();
      throw new Error(`Run Command failed: ${response.status} ${errorText}`);
    }

    // 202 Accepted - need to poll the location header
    if (response.status === 202) {
      const locationUrl = response.headers.get('location') || response.headers.get('azure-asyncoperation');
      if (!locationUrl) {
        throw new Error('Run Command returned 202 but no location header for polling');
      }

      console.log('🏴‍☠️ Run Command accepted, polling for result...');
      return this.pollRunCommandResult(locationUrl, onProgress);
    }

    // 200 OK - result inline (rare, but possible for very fast commands)
    const result = await response.json();
    return this.parseRunCommandResult(result);
  }

  /**
   * Poll the async operation URL until Run Command completes
   * Max polling time: 90 seconds (Azure Run Command timeout)
   */
  private async pollRunCommandResult(
    locationUrl: string,
    onProgress?: (progress: PollingProgress) => void
  ): Promise<RunCommandResult> {
    const token = await this.tokenStorage.getAccessToken();
    const maxAttempts = 30; // 30 * 3s = 90 seconds max
    const pollInterval = 3000; // 3 seconds

    for (let attempt = 0; attempt < maxAttempts; attempt++) {
      const attemptNum = attempt + 1;
      console.log(`🏴‍☠️ Polling Run Command result (attempt ${attemptNum}/${maxAttempts})...`);

      // Report progress to UI
      if (onProgress) {
        onProgress({
          attempt: attemptNum,
          maxAttempts,
          message: `Waiting for VM response... (${attemptNum}/${maxAttempts})`,
        });
      }

      const response = await fetch(locationUrl, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });

      if (response.status === 202) {
        // Still running, wait and retry
        await new Promise(resolve => setTimeout(resolve, pollInterval));
        continue;
      }

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`Run Command polling failed: ${response.status} ${errorText}`);
      }

      // Operation completed
      const result = await response.json();
      console.log('🏴‍☠️ Run Command completed:', result);
      return this.parseRunCommandResult(result);
    }

    throw new Error('Run Command timed out after 90 seconds');
  }

  /**
   * Parse Run Command API response
   *
   * Azure Run Command returns response in format:
   * {
   *   "value": [{
   *     "code": "ProvisioningState/succeeded",
   *     "message": "Enable succeeded: \n[stdout]\n...\n\n[stderr]\n..."
   *   }]
   * }
   *
   * We need to parse stdout and stderr from the single message field.
   */
  private parseRunCommandResult(response: any): RunCommandResult {
    const value = response.value || [];
    const firstValue = value[0] || {};

    // Check if command succeeded - look for "succeeded" in code
    const code = firstValue.code || '';
    const succeeded = code.toLowerCase().includes('succeeded');

    // Parse stdout and stderr from message field
    // Format: "Enable succeeded: \n[stdout]\n...\n\n[stderr]\n..."
    const message = firstValue.message || '';
    let stdout = '';
    let stderr = '';

    // Extract content between [stdout] and [stderr] markers
    const stdoutMatch = message.match(/\[stdout\]\n([\s\S]*?)\n\n\[stderr\]/);
    const stderrMatch = message.match(/\[stderr\]\n([\s\S]*)$/);

    if (stdoutMatch) {
      stdout = stdoutMatch[1].trim();
    }
    if (stderrMatch) {
      stderr = stderrMatch[1].trim();
    }

    console.log('🏴‍☠️ Parsed Run Command result:', { code, succeeded, stdoutLen: stdout.length, stderrLen: stderr.length });

    return {
      exitCode: succeeded ? 0 : 1,
      stdout,
      stderr,
      executionTime: firstValue.displayStatus,
    };
  }
}

export default AzureClient;
