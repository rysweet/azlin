/**
 * VM Creation Hook
 *
 * Orchestrates the complete VM creation workflow:
 * 1. Create/verify VNet
 * 2. Create/verify Subnet
 * 3. Create Public IP (if needed)
 * 4. Create Network Interface
 * 5. Create VM
 * 6. Poll until complete
 *
 * Philosophy:
 * - Single responsibility: VM creation orchestration
 * - Error recovery with clear rollback
 * - Progress tracking at each stage
 * - Zero-BS: Real Azure API integration
 */

import { useState, useCallback } from 'react';
import { AzureClient, VmCreationRequestApi } from '../../../api/azure-client';
import { VmCreationRequest, VmCreationProgress } from '../types/VmWizardTypes';
import { createLogger } from '../../../utils/logger';

const logger = createLogger('[useVmCreation]');

// ============================================================================
// Creation Stages with Progress Tracking
// ============================================================================

// Creation stages for progress tracking (to be used when implementing progress UI)
// const CREATION_STAGES: StageDefinition[] = [
//   { stage: 'vnet', label: 'Creating virtual network', progress: 10, estimatedSeconds: 30 },
//   { stage: 'subnet', label: 'Configuring subnet', progress: 30, estimatedSeconds: 20 },
//   { stage: 'nic', label: 'Setting up network interface', progress: 50, estimatedSeconds: 40 },
//   { stage: 'vm', label: 'Creating virtual machine', progress: 80, estimatedSeconds: 600 },
//   { stage: 'ready', label: 'VM ready', progress: 100, estimatedSeconds: 0 },
// ];

// ============================================================================
// Hook Interface
// ============================================================================

export interface UseVmCreationReturn {
  createVm: (request: VmCreationRequest) => Promise<string>;
  isCreating: boolean;
  progress: VmCreationProgress | null;
  error: string | null;
}

export function useVmCreation(
  onProgress?: (progress: VmCreationProgress) => void
): UseVmCreationReturn {
  const [isCreating, setIsCreating] = useState(false);
  const [progress, setProgress] = useState<VmCreationProgress | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Update progress and notify callback
  const updateProgress = useCallback((newProgress: VmCreationProgress) => {
    setProgress(newProgress);
    if (onProgress) {
      onProgress(newProgress);
    }
  }, [onProgress]);

  // Get Azure client instance
  const getAzureClient = useCallback(() => {
    const subscriptionId = import.meta.env.VITE_AZURE_SUBSCRIPTION_ID?.trim() || '';
    return new AzureClient(subscriptionId);
  }, []);

  /**
   * Main VM creation orchestration function
   * Returns VM ID on success, throws on error
   */
  const createVm = useCallback(async (request: VmCreationRequest): Promise<string> => {
    logger.debug('Starting VM creation:', request);
    setIsCreating(true);
    setError(null);

    const client = getAzureClient();
    const { basics, size, image, network, auth } = request;

    // Track created resources for potential rollback
    const createdResources: { type: string; id: string }[] = [];

    try {
      // ========================================================================
      // Stage 1: Create/Verify Virtual Network
      // ========================================================================
      updateProgress({
        stage: 'vnet',
        progress: 10,
        estimatedTimeRemaining: 90,
        message: 'Creating virtual network...',
      });

      const vnet = await client.createOrGetVirtualNetwork(
        basics.resourceGroup,
        basics.location,
        network.vnet,
        '10.0.0.0/16'  // Default VNet CIDR
      );

      logger.debug('VNet ready:', vnet.name);
      createdResources.push({ type: 'vnet', id: vnet.id });

      // ========================================================================
      // Stage 2: Create/Verify Subnet
      // ========================================================================
      updateProgress({
        stage: 'subnet',
        progress: 30,
        estimatedTimeRemaining: 70,
        message: 'Configuring subnet...',
      });

      const subnet = await client.createOrGetSubnet(
        basics.resourceGroup,
        network.vnet,
        network.subnet,
        '10.0.1.0/24'  // Default Subnet CIDR
      );

      logger.debug('Subnet ready:', subnet.name);
      createdResources.push({ type: 'subnet', id: subnet.id });

      // ========================================================================
      // Stage 3: Create Network Interface (with optional Public IP)
      // ========================================================================
      updateProgress({
        stage: 'nic',
        progress: 50,
        estimatedTimeRemaining: 50,
        message: 'Setting up network interface...',
      });

      let publicIpId: string | undefined;

      // Create Public IP if requested
      if (network.publicIp) {
        const publicIpName = `${basics.vmName}-ip`;
        const publicIp = await client.createPublicIpAddress(
          basics.resourceGroup,
          basics.location,
          publicIpName
        );

        logger.debug('Public IP created:', publicIp.name);
        createdResources.push({ type: 'publicip', id: publicIp.id });
        publicIpId = publicIp.id;
      }

      // Create Network Interface
      const nicName = `${basics.vmName}-nic`;
      const nic = await client.createNetworkInterface(
        basics.resourceGroup,
        basics.location,
        nicName,
        subnet.id,
        publicIpId
      );

      logger.debug('NIC created:', nic.name);
      createdResources.push({ type: 'nic', id: nic.id });

      // ========================================================================
      // Stage 4: Create Virtual Machine
      // ========================================================================
      updateProgress({
        stage: 'vm',
        progress: 80,
        estimatedTimeRemaining: 600,  // 10 minutes estimated
        message: 'Creating virtual machine...',
      });

      const vmRequest: VmCreationRequestApi = {
        resourceGroup: basics.resourceGroup,
        location: basics.location,
        vmName: basics.vmName,
        vmSize: size.vmSize,
        imagePublisher: image.publisher,
        imageOffer: image.offer,
        imageSku: image.sku,
        imageVersion: image.version,
        adminUsername: auth.username,
        sshPublicKey: auth.sshPublicKey,
        nicId: nic.id,
      };

      const operationUrl = await client.createVirtualMachine(vmRequest);
      logger.debug('VM creation started, polling...');

      // Poll creation status
      const vmId = await client.pollVmCreationStatus(
        operationUrl,
        (pollProgress) => {
          // Update progress during polling
          updateProgress({
            stage: 'vm',
            progress: 80 + (pollProgress.attempt / pollProgress.maxAttempts) * 19,  // 80-99%
            estimatedTimeRemaining: (pollProgress.maxAttempts - pollProgress.attempt) * 5,
            message: pollProgress.message,
          });
        }
      );

      logger.debug('VM created successfully:', vmId);

      // ========================================================================
      // Stage 5: Complete
      // ========================================================================
      updateProgress({
        stage: 'ready',
        progress: 100,
        estimatedTimeRemaining: 0,
        message: 'VM ready!',
      });

      setIsCreating(false);
      return vmId;

    } catch (err: any) {
      logger.error('VM creation failed:', err);

      // Update progress with error
      updateProgress({
        stage: 'error',
        progress: 0,
        estimatedTimeRemaining: 0,
        message: err.message || 'VM creation failed',
      });

      setError(err.message || 'VM creation failed');
      setIsCreating(false);

      // TODO: Implement rollback of created resources
      // For now, just log what was created
      logger.warn('Rollback not implemented. Created resources:', createdResources);

      throw err;
    }
  }, [getAzureClient, updateProgress]);

  return {
    createVm,
    isCreating,
    progress,
    error,
  };
}

export default useVmCreation;
