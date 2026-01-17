/**
 * VM Redux Store for Azlin Mobile PWA
 *
 * State management for Azure VMs using Redux Toolkit.
 * Handles VM listing, start/stop operations, and state updates.
 *
 * Philosophy:
 * - Single responsibility: VM state management
 * - Self-contained with clear selectors
 * - Zero-BS: Real Azure API integration via thunks
 */

import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit';
import { AzureClient, VMInfo } from '../api/azure-client';

interface VMState {
  items: VMInfo[];
  loading: boolean;
  error: string | null;
  lastSync: number | null;
}

const initialState: VMState = {
  items: [],
  loading: false,
  error: null,
  lastSync: null,
};

// Create Azure client instance
const getAzureClient = () => {
  const subscriptionId = import.meta.env.VITE_AZURE_SUBSCRIPTION_ID?.trim() || '';
  console.log('🏴‍☠️ Creating Azure client with subscription:', subscriptionId);
  return new AzureClient(subscriptionId);
};

/**
 * Get the configured resource group for azlin VMs
 */
function getAzlinResourceGroup(): string | undefined {
  return import.meta.env.VITE_AZURE_RESOURCE_GROUP?.trim() || undefined;
}

/**
 * Async thunk to fetch all VMs from the azlin resource group
 */
export const fetchVMs = createAsyncThunk<VMInfo[], string | undefined>(
  'vms/fetchAll',
  async (resourceGroupOverride) => {
    // Use override if provided, otherwise use configured resource group
    const resourceGroup = resourceGroupOverride || getAzlinResourceGroup();
    console.log('🏴‍☠️ fetchVMs thunk called', { resourceGroup });

    try {
      const client = getAzureClient();
      console.log('🏴‍☠️ Azure client created, calling listVMs...');

      // Fetch VMs from the specific resource group (azlin VMs)
      const vms = await client.listVMs(resourceGroup);
      console.log('🏴‍☠️ listVMs returned:', vms.length, 'VMs from', resourceGroup || 'all resource groups');

      return vms;
    } catch (error) {
      console.error('🏴‍☠️ fetchVMs failed:', error);
      throw error;
    }
  }
);

/**
 * Async thunk to start a VM
 */
export const startVM = createAsyncThunk<
  { resourceGroup: string; vmName: string; powerState: string },
  { resourceGroup: string; vmName: string }
>(
  'vms/start',
  async ({ resourceGroup, vmName }) => {
    const client = getAzureClient();
    await client.startVM(resourceGroup, vmName);
    return { resourceGroup, vmName, powerState: 'running' };
  }
);

/**
 * Async thunk to stop/deallocate a VM
 */
export const stopVM = createAsyncThunk<
  { resourceGroup: string; vmName: string; powerState: string },
  { resourceGroup: string; vmName: string; deallocate?: boolean }
>(
  'vms/stop',
  async ({ resourceGroup, vmName, deallocate = true }) => {
    const client = getAzureClient();
    await client.stopVM(resourceGroup, vmName, deallocate);
    return {
      resourceGroup,
      vmName,
      powerState: deallocate ? 'deallocated' : 'stopped',
    };
  }
);

const vmSlice = createSlice({
  name: 'vms',
  initialState,
  reducers: {},
  extraReducers: (builder) => {
    // fetchVMs
    builder
      .addCase(fetchVMs.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(fetchVMs.fulfilled, (state, action: PayloadAction<VMInfo[]>) => {
        state.items = action.payload;
        state.loading = false;
        state.error = null;
        state.lastSync = Date.now();
      })
      .addCase(fetchVMs.rejected, (state, action) => {
        state.loading = false;
        state.error = action.error.message || 'Failed to fetch VMs';
      });

    // startVM
    builder
      .addCase(startVM.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(startVM.fulfilled, (state, action) => {
        const vm = state.items.find(v => v.name === action.payload.vmName);
        if (vm) {
          vm.powerState = action.payload.powerState;
        }
        state.loading = false;
      })
      .addCase(startVM.rejected, (state, action) => {
        state.loading = false;
        state.error = action.error.message || 'Failed to start VM';
      });

    // stopVM
    builder
      .addCase(stopVM.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(stopVM.fulfilled, (state, action) => {
        const vm = state.items.find(v => v.name === action.payload.vmName);
        if (vm) {
          vm.powerState = action.payload.powerState;
        }
        state.loading = false;
      })
      .addCase(stopVM.rejected, (state, action) => {
        state.loading = false;
        state.error = action.error.message || 'Failed to stop VM';
      });
  },
});

// Selectors
export const selectAllVMs = (state: { vms: VMState }) => state.vms.items;

export const selectVMById = (state: { vms: VMState }, id: string) =>
  state.vms.items.find(vm => vm.id === id);

export const selectVMsByPowerState = (state: { vms: VMState }, powerState: string) =>
  state.vms.items.filter(vm => vm.powerState === powerState);

export const selectIsLoading = (state: { vms: VMState }) => state.vms.loading;

export const selectError = (state: { vms: VMState }) => state.vms.error;

export const selectLastSync = (state: { vms: VMState }) => state.vms.lastSync;

export default vmSlice.reducer;
