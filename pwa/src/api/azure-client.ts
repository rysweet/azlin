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
import { createLogger } from '../utils/logger';

const logger = createLogger('[AzureClient]');
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
  instanceViewAvailable: boolean;
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
      logger.debug(`VM busy (409 Conflict), trying again in ${delay / 1000}s... (attempt ${retryCount + 1}/${MAX_RETRIES})`);

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
          logger.error('Azure API error response:', errorBody);
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
      // For non-JSON responses (typically 202 Accepted), return null
      // Caller must handle null return for these cases
      logger.debug('Non-JSON response received, returning null');
      return null as T;
    }

    const text = await response.text();
    if (!text || text.trim() === '') {
      logger.debug('Empty response body, returning null');
      return null as T;
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
    logger.debug('listVMs called', { subscriptionId: this.subscriptionId, resourceGroup });

    const basePath = resourceGroup
      ? `/subscriptions/${this.subscriptionId}/resourceGroups/${resourceGroup}/providers/Microsoft.Compute/virtualMachines`
      : `/subscriptions/${this.subscriptionId}/providers/Microsoft.Compute/virtualMachines`;

    logger.debug('Calling Azure API:', basePath);

    try {
      // First get the list of VMs
      const response = await this.get<{ value: Array<unknown> }>(basePath);

      // Validate response structure
      if (!response || !Array.isArray(response.value)) {
        logger.error('Invalid response structure from Azure API:', response);
        throw new Error('Azure API returned unexpected response format - missing value array');
      }

      logger.debug('Azure API response:', { count: response.value.length });

      // Then fetch instance view for each VM to get power state
      const vmsWithStatus = await Promise.all(
        response.value.map(async (vm: any) => {
          try {
            // Get instance view for this specific VM
            const instanceViewPath = `${vm.id}/instanceView`;
            const instanceView = await this.get<any>(instanceViewPath);
            // Merge instance view into VM data
            return { ...vm, properties: { ...vm.properties, instanceView }, instanceViewAvailable: true };
          } catch (e) {
            logger.warn(`Failed to get instance view for ${vm.name}:`, e);
            return { ...vm, instanceViewAvailable: false };
          }
        })
      );

      const vms = vmsWithStatus.map((vm: any) => this.parseVM(vm));
      logger.debug('Parsed VMs:', vms.length, vms);

      return vms;
    } catch (error) {
      logger.error('Failed to list VMs:', error);
      throw error;
    }
  }

  /**
   * Parse Azure VM response to VMInfo
   */
  private parseVM(raw: any): VMInfo {
    // Validate required fields
    if (!raw.id || !raw.name || !raw.location) {
      throw new Error('Invalid VM data: missing required fields (id, name, or location)');
    }

    // Extract resource group from ID
    const idParts = raw.id.split('/');
    const resourceGroup = idParts[4];
    if (!resourceGroup) {
      throw new Error(`Could not extract resource group from VM ID: ${raw.id}`);
    }

    // Extract power state from instanceView statuses
    let powerState = 'unknown';
    const instanceViewAvailable = raw.instanceViewAvailable ?? false;
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
    const networkInterfaces = raw.properties?.networkProfile?.networkInterfaces;
    if (Array.isArray(networkInterfaces) && networkInterfaces.length > 0) {
      const firstNic = networkInterfaces[0];
      if (firstNic?.properties?.privateIPAddress) {
        privateIP = firstNic.properties.privateIPAddress;
      }
    }

    // Extract hardware profile with validation
    const vmSize = raw.properties?.hardwareProfile?.vmSize;
    if (!vmSize) {
      logger.warn(`VM ${raw.name} missing vmSize, using 'Unknown'`);
    }

    // Extract OS type with validation
    const osType = raw.properties?.storageProfile?.osDisk?.osType;
    if (!osType) {
      logger.warn(`VM ${raw.name} missing osType, using 'Unknown'`);
    }

    return {
      id: raw.id,
      name: raw.name,
      resourceGroup,
      location: raw.location,
      size: vmSize || 'Unknown',
      powerState,
      privateIP,
      osType: osType || 'Unknown',
      tags: raw.tags || {},
      instanceViewAvailable,
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

    logger.debug('Executing Run Command on', vmName);

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

      logger.debug('Run Command accepted, polling for result...');
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
      logger.debug(`Polling Run Command result (attempt ${attemptNum}/${maxAttempts})...`);

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
      logger.debug('Run Command completed:', result);
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

    logger.debug('Parsed Run Command result:', { code, succeeded, stdoutLen: stdout.length, stderrLen: stderr.length });

    return {
      exitCode: succeeded ? 0 : 1,
      stdout,
      stderr,
      executionTime: firstValue.displayStatus,
    };
  }

  // ============================================================================
  // Network Management APIs (for VM Creation Wizard)
  // ============================================================================

  /**
   * List Virtual Networks in a resource group
   */
  async listVirtualNetworks(resourceGroup: string): Promise<VNetInfo[]> {
    const path = `/subscriptions/${this.subscriptionId}/resourceGroups/${resourceGroup}/providers/Microsoft.Network/virtualNetworks`;
    const response = await this.get<{ value: Array<any> }>(path);

    if (!response || !Array.isArray(response.value)) {
      return [];
    }

    return response.value.map((vnet: any) => ({
      id: vnet.id,
      name: vnet.name,
      location: vnet.location,
      addressPrefixes: vnet.properties?.addressSpace?.addressPrefixes || [],
    }));
  }

  /**
   * Create or get existing Virtual Network
   * If VNet exists, returns existing. If not, creates new with specified CIDR.
   */
  async createOrGetVirtualNetwork(
    resourceGroup: string,
    location: string,
    vnetName: string,
    addressPrefix: string = '10.0.0.0/16'
  ): Promise<VNetInfo> {
    logger.debug('Creating/getting VNet:', { resourceGroup, location, vnetName, addressPrefix });

    const path = `/subscriptions/${this.subscriptionId}/resourceGroups/${resourceGroup}/providers/Microsoft.Network/virtualNetworks/${vnetName}`;

    try {
      // Try to get existing VNet first
      const existing = await this.get<any>(path);
      if (existing) {
        logger.debug('VNet already exists:', existing.name);
        return {
          id: existing.id,
          name: existing.name,
          location: existing.location,
          addressPrefixes: existing.properties?.addressSpace?.addressPrefixes || [addressPrefix],
        };
      }
    } catch (error: any) {
      // 404 means doesn't exist, create it
      if (!error.message?.includes('404')) {
        throw error;  // Re-throw if not a 404
      }
    }

    // Create new VNet
    const vnetBody = {
      location,
      properties: {
        addressSpace: {
          addressPrefixes: [addressPrefix],
        },
      },
    };

    const created = await this.put<any>(path, vnetBody);
    logger.debug('VNet created:', created.name);

    return {
      id: created.id,
      name: created.name,
      location: created.location,
      addressPrefixes: created.properties?.addressSpace?.addressPrefixes || [addressPrefix],
    };
  }

  /**
   * List Subnets in a Virtual Network
   */
  async listSubnets(resourceGroup: string, vnetName: string): Promise<SubnetInfo[]> {
    const path = `/subscriptions/${this.subscriptionId}/resourceGroups/${resourceGroup}/providers/Microsoft.Network/virtualNetworks/${vnetName}/subnets`;
    const response = await this.get<{ value: Array<any> }>(path);

    if (!response || !Array.isArray(response.value)) {
      return [];
    }

    return response.value.map((subnet: any) => ({
      id: subnet.id,
      name: subnet.name,
      addressPrefix: subnet.properties?.addressPrefix || '',
      vnetName,
    }));
  }

  /**
   * Create or get existing Subnet in a VNet
   * Subnet CIDR must be within VNet CIDR range.
   */
  async createOrGetSubnet(
    resourceGroup: string,
    vnetName: string,
    subnetName: string,
    addressPrefix: string = '10.0.1.0/24'
  ): Promise<SubnetInfo> {
    logger.debug('Creating/getting Subnet:', { resourceGroup, vnetName, subnetName, addressPrefix });

    const path = `/subscriptions/${this.subscriptionId}/resourceGroups/${resourceGroup}/providers/Microsoft.Network/virtualNetworks/${vnetName}/subnets/${subnetName}`;

    try {
      // Try to get existing subnet first
      const existing = await this.get<any>(path);
      if (existing) {
        logger.debug('Subnet already exists:', existing.name);
        return {
          id: existing.id,
          name: existing.name,
          addressPrefix: existing.properties?.addressPrefix || addressPrefix,
          vnetName,
        };
      }
    } catch (error: any) {
      // 404 means doesn't exist, create it
      if (!error.message?.includes('404')) {
        throw error;  // Re-throw if not a 404
      }
    }

    // Create new Subnet
    const subnetBody = {
      properties: {
        addressPrefix,
      },
    };

    const created = await this.put<any>(path, subnetBody);
    logger.debug('Subnet created:', created.name);

    return {
      id: created.id,
      name: created.name,
      addressPrefix: created.properties?.addressPrefix || addressPrefix,
      vnetName,
    };
  }

  /**
   * Create Public IP Address (optional for VM)
   */
  async createPublicIpAddress(
    resourceGroup: string,
    location: string,
    publicIpName: string
  ): Promise<PublicIpInfo> {
    logger.debug('Creating Public IP:', { resourceGroup, location, publicIpName });

    const path = `/subscriptions/${this.subscriptionId}/resourceGroups/${resourceGroup}/providers/Microsoft.Network/publicIPAddresses/${publicIpName}`;

    const publicIpBody = {
      location,
      properties: {
        publicIPAllocationMethod: 'Static',
        publicIPAddressVersion: 'IPv4',
      },
      sku: {
        name: 'Standard',
      },
    };

    const created = await this.put<any>(path, publicIpBody);
    logger.debug('Public IP created:', created.name);

    return {
      id: created.id,
      name: created.name,
      ipAddress: created.properties?.ipAddress || '',
    };
  }

  /**
   * Create Network Interface Card (NIC)
   * NIC connects VM to subnet and optionally to public IP.
   */
  async createNetworkInterface(
    resourceGroup: string,
    location: string,
    nicName: string,
    subnetId: string,
    publicIpId?: string
  ): Promise<NetworkInterfaceInfo> {
    logger.debug('Creating NIC:', { resourceGroup, location, nicName, subnetId, publicIpId });

    const path = `/subscriptions/${this.subscriptionId}/resourceGroups/${resourceGroup}/providers/Microsoft.Network/networkInterfaces/${nicName}`;

    const ipConfig: any = {
      name: 'ipconfig1',
      properties: {
        subnet: {
          id: subnetId,
        },
        privateIPAllocationMethod: 'Dynamic',
      },
    };

    // Add public IP if provided
    if (publicIpId) {
      ipConfig.properties.publicIPAddress = {
        id: publicIpId,
      };
    }

    const nicBody = {
      location,
      properties: {
        ipConfigurations: [ipConfig],
      },
    };

    const created = await this.put<any>(path, nicBody);
    logger.debug('NIC created:', created.name);

    return {
      id: created.id,
      name: created.name,
      privateIpAddress: created.properties?.ipConfigurations?.[0]?.properties?.privateIPAddress || '',
      publicIpAddress: created.properties?.ipConfigurations?.[0]?.properties?.publicIPAddress?.properties?.ipAddress,
    };
  }

  /**
   * Create Virtual Machine
   * This is the final step in VM creation after networking is set up.
   *
   * Returns operation URL for polling creation status.
   */
  async createVirtualMachine(request: VmCreationRequestApi): Promise<string> {
    logger.debug('Creating VM:', request);

    const path = `/subscriptions/${this.subscriptionId}/resourceGroups/${request.resourceGroup}/providers/Microsoft.Compute/virtualMachines/${request.vmName}`;

    const vmBody = {
      location: request.location,
      properties: {
        hardwareProfile: {
          vmSize: request.vmSize,
        },
        osProfile: {
          computerName: request.vmName,
          adminUsername: request.adminUsername,
          linuxConfiguration: {
            disablePasswordAuthentication: true,
            ssh: {
              publicKeys: [
                {
                  path: `/home/${request.adminUsername}/.ssh/authorized_keys`,
                  keyData: request.sshPublicKey,
                },
              ],
            },
          },
        },
        storageProfile: {
          imageReference: {
            publisher: request.imagePublisher,
            offer: request.imageOffer,
            sku: request.imageSku,
            version: request.imageVersion || 'latest',
          },
          osDisk: {
            createOption: 'FromImage',
            managedDisk: {
              storageAccountType: 'Standard_LRS',  // Standard HDD
            },
          },
        },
        networkProfile: {
          networkInterfaces: [
            {
              id: request.nicId,
              properties: {
                primary: true,
              },
            },
          ],
        },
      },
    };

    // PUT request returns 201 with Azure-AsyncOperation header for long-running operation
    const token = await this.tokenStorage.getAccessToken();
    const url = new URL(`${AZURE_BASE_URL}${path}`);
    url.searchParams.set('api-version', API_VERSION);

    const response = await fetch(url.toString(), {
      method: 'PUT',
      headers: {
        'Authorization': `Bearer ${token}`,
        'Content-Type': 'application/json',
      },
      body: JSON.stringify(vmBody),
    });

    if (!response.ok && response.status !== 201) {
      const errorText = await response.text();
      throw new Error(`VM creation failed: ${response.status} ${errorText}`);
    }

    // Get operation URL for polling
    const operationUrl = response.headers.get('azure-asyncoperation') || response.headers.get('location');
    if (!operationUrl) {
      throw new Error('VM creation started but no operation URL returned for polling');
    }

    logger.debug('VM creation started, operation URL:', operationUrl);
    return operationUrl;
  }

  /**
   * Poll async operation status until completion
   * Used for VM creation, which can take 5-15 minutes.
   *
   * Returns final VM ID when complete.
   */
  async pollVmCreationStatus(
    operationUrl: string,
    onProgress?: (progress: { attempt: number; maxAttempts: number; message: string }) => void
  ): Promise<string> {
    const token = await this.tokenStorage.getAccessToken();
    const maxAttempts = 180; // 180 * 5s = 15 minutes max
    const pollInterval = 5000; // 5 seconds

    for (let attempt = 0; attempt < maxAttempts; attempt++) {
      const attemptNum = attempt + 1;
      logger.debug(`Polling VM creation status (attempt ${attemptNum}/${maxAttempts})...`);

      if (onProgress) {
        onProgress({
          attempt: attemptNum,
          maxAttempts,
          message: `Creating VM... (${attemptNum}/${maxAttempts})`,
        });
      }

      const response = await fetch(operationUrl, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      });

      if (!response.ok) {
        const errorText = await response.text();
        throw new Error(`VM creation polling failed: ${response.status} ${errorText}`);
      }

      const result = await response.json();
      const status = result.status?.toLowerCase();

      logger.debug('VM creation status:', status);

      if (status === 'succeeded') {
        // Operation complete, extract VM ID from result
        const vmId = result.properties?.output?.id || result.id;
        if (!vmId) {
          throw new Error('VM creation succeeded but no VM ID returned');
        }
        logger.debug('VM creation completed:', vmId);
        return vmId;
      }

      if (status === 'failed') {
        const errorMessage = result.properties?.statusMessage || result.error?.message || 'Unknown error';
        throw new Error(`VM creation failed: ${errorMessage}`);
      }

      // Still in progress, wait and retry
      await new Promise(resolve => setTimeout(resolve, pollInterval));
    }

    throw new Error('VM creation timed out after 15 minutes');
  }

  /**
   * List Azure regions (locations) available for subscription
   */
  async listLocations(): Promise<AzureLocationInfo[]> {
    const path = `/subscriptions/${this.subscriptionId}/locations`;
    const response = await this.get<{ value: Array<any> }>(path);

    if (!response || !Array.isArray(response.value)) {
      return [];
    }

    return response.value.map((location: any) => ({
      name: location.name,
      displayName: location.displayName,
      regionalDisplayName: location.regionalDisplayName || location.displayName,
    }));
  }
}

// ============================================================================
// Additional Type Interfaces for VM Creation
// ============================================================================

export interface VNetInfo {
  id: string;
  name: string;
  location: string;
  addressPrefixes: string[];
}

export interface SubnetInfo {
  id: string;
  name: string;
  addressPrefix: string;
  vnetName: string;
}

export interface PublicIpInfo {
  id: string;
  name: string;
  ipAddress: string;
}

export interface NetworkInterfaceInfo {
  id: string;
  name: string;
  privateIpAddress: string;
  publicIpAddress?: string;
}

export interface VmCreationRequestApi {
  resourceGroup: string;
  location: string;
  vmName: string;
  vmSize: string;
  imagePublisher: string;
  imageOffer: string;
  imageSku: string;
  imageVersion: string;
  adminUsername: string;
  sshPublicKey: string;
  nicId: string;
}

export interface AzureLocationInfo {
  name: string;             // e.g., "eastus"
  displayName: string;      // e.g., "East US"
  regionalDisplayName: string;
}

export default AzureClient;
