/**
 * Unit Tests for VM Redux Store (60% of testing pyramid)
 *
 * Tests Redux Toolkit slice for VM state management.
 * These tests WILL FAIL until vm-store.ts is implemented.
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { configureStore } from '@reduxjs/toolkit';
import vmReducer, {
  fetchVMs,
  startVM,
  stopVM,
  selectAllVMs,
  selectVMById,
  selectVMsByPowerState,
  selectIsLoading,
  selectError,
} from '../vm-store';

describe('VM Store', () => {
  let store: ReturnType<typeof configureStore>;

  beforeEach(() => {
    store = configureStore({
      reducer: {
        vms: vmReducer,
      },
    });
  });

  describe('initial state', () => {
    it('should have empty items array', () => {
      const state = store.getState().vms;
      expect(state.items).toEqual([]);
    });

    it('should not be loading', () => {
      const state = store.getState().vms;
      expect(state.loading).toBe(false);
    });

    it('should have no error', () => {
      const state = store.getState().vms;
      expect(state.error).toBeNull();
    });

    it('should have null lastSync', () => {
      const state = store.getState().vms;
      expect(state.lastSync).toBeNull();
    });
  });

  describe('fetchVMs thunk', () => {
    it('should set loading to true when pending', () => {
      store.dispatch(fetchVMs.pending('', undefined));

      const state = store.getState().vms;
      expect(state.loading).toBe(true);
      // Will fail until implemented
    });

    it('should set items and lastSync when fulfilled', () => {
      const mockVMs = [
        {
          id: 'vm-1',
          name: 'test-vm-1',
          resourceGroup: 'rg-test',
          powerState: 'running',
          size: 'Standard_B2s',
          location: 'eastus',
        },
        {
          id: 'vm-2',
          name: 'test-vm-2',
          resourceGroup: 'rg-test',
          powerState: 'deallocated',
          size: 'Standard_D2s_v3',
          location: 'westus2',
        },
      ];

      store.dispatch(fetchVMs.fulfilled(mockVMs, '', undefined));

      const state = store.getState().vms;
      expect(state.items).toEqual(mockVMs);
      expect(state.loading).toBe(false);
      expect(state.lastSync).toBeDefined();
      expect(state.lastSync).toBeGreaterThan(0);
    });

    it('should set error when rejected', () => {
      const error = new Error('Failed to fetch VMs');

      store.dispatch(fetchVMs.rejected(error, '', undefined));

      const state = store.getState().vms;
      expect(state.loading).toBe(false);
      expect(state.error).toBe('Failed to fetch VMs');
    });

    it('should clear previous error on successful fetch', () => {
      // Set error first
      store.dispatch(fetchVMs.rejected(new Error('Previous error'), '', undefined));
      expect(store.getState().vms.error).toBeTruthy();

      // Successful fetch should clear error
      store.dispatch(fetchVMs.fulfilled([], '', undefined));
      expect(store.getState().vms.error).toBeNull();
    });
  });

  describe('startVM thunk', () => {
    beforeEach(() => {
      // Setup initial state with VMs
      const mockVMs = [
        {
          id: 'vm-1',
          name: 'test-vm',
          resourceGroup: 'rg-test',
          powerState: 'deallocated',
          size: 'Standard_B2s',
          location: 'eastus',
        },
      ];
      store.dispatch(fetchVMs.fulfilled(mockVMs, '', undefined));
    });

    it('should update VM power state to running when fulfilled', () => {
      store.dispatch(
        startVM.fulfilled(
          { resourceGroup: 'rg-test', vmName: 'test-vm', powerState: 'running' },
          '',
          { resourceGroup: 'rg-test', vmName: 'test-vm' }
        )
      );

      const state = store.getState().vms;
      const vm = state.items.find(v => v.name === 'test-vm');
      expect(vm?.powerState).toBe('running');
      // Will fail until implemented
    });

    it('should not modify other VMs', () => {
      const initialVMs = [...store.getState().vms.items];

      store.dispatch(
        startVM.fulfilled(
          { resourceGroup: 'rg-test', vmName: 'test-vm', powerState: 'running' },
          '',
          { resourceGroup: 'rg-test', vmName: 'test-vm' }
        )
      );

      const state = store.getState().vms;
      expect(state.items.length).toBe(initialVMs.length);
    });

    it('should handle VM not found gracefully', () => {
      store.dispatch(
        startVM.fulfilled(
          { resourceGroup: 'rg-test', vmName: 'nonexistent', powerState: 'running' },
          '',
          { resourceGroup: 'rg-test', vmName: 'nonexistent' }
        )
      );

      // Should not throw error
      expect(store.getState().vms.items).toBeDefined();
    });

    it('should set error when start fails', () => {
      const error = new Error('Failed to start VM');

      store.dispatch(
        startVM.rejected(error, '', { resourceGroup: 'rg-test', vmName: 'test-vm' })
      );

      const state = store.getState().vms;
      expect(state.error).toBeTruthy();
    });
  });

  describe('stopVM thunk', () => {
    beforeEach(() => {
      const mockVMs = [
        {
          id: 'vm-1',
          name: 'test-vm',
          resourceGroup: 'rg-test',
          powerState: 'running',
          size: 'Standard_B2s',
          location: 'eastus',
        },
      ];
      store.dispatch(fetchVMs.fulfilled(mockVMs, '', undefined));
    });

    it('should update VM power state to deallocated', () => {
      store.dispatch(
        stopVM.fulfilled(
          {
            resourceGroup: 'rg-test',
            vmName: 'test-vm',
            powerState: 'deallocated',
          },
          '',
          { resourceGroup: 'rg-test', vmName: 'test-vm', deallocate: true }
        )
      );

      const state = store.getState().vms;
      const vm = state.items.find(v => v.name === 'test-vm');
      expect(vm?.powerState).toBe('deallocated');
      // Will fail until implemented
    });

    it('should update VM power state to stopped when not deallocating', () => {
      store.dispatch(
        stopVM.fulfilled(
          { resourceGroup: 'rg-test', vmName: 'test-vm', powerState: 'stopped' },
          '',
          { resourceGroup: 'rg-test', vmName: 'test-vm', deallocate: false }
        )
      );

      const state = store.getState().vms;
      const vm = state.items.find(v => v.name === 'test-vm');
      expect(vm?.powerState).toBe('stopped');
    });
  });

  describe('selectors', () => {
    beforeEach(() => {
      const mockVMs = [
        {
          id: 'vm-1',
          name: 'test-vm-1',
          resourceGroup: 'rg-test',
          powerState: 'running',
          size: 'Standard_B2s',
          location: 'eastus',
        },
        {
          id: 'vm-2',
          name: 'test-vm-2',
          resourceGroup: 'rg-test',
          powerState: 'deallocated',
          size: 'Standard_D2s_v3',
          location: 'westus2',
        },
        {
          id: 'vm-3',
          name: 'test-vm-3',
          resourceGroup: 'rg-test',
          powerState: 'running',
          size: 'Standard_B1s',
          location: 'eastus',
        },
      ];
      store.dispatch(fetchVMs.fulfilled(mockVMs, '', undefined));
    });

    describe('selectAllVMs', () => {
      it('should return all VMs', () => {
        const vms = selectAllVMs(store.getState());
        expect(vms).toHaveLength(3);
        // Will fail until implemented
      });
    });

    describe('selectVMById', () => {
      it('should return VM by ID', () => {
        const vm = selectVMById(store.getState(), 'vm-1');
        expect(vm?.name).toBe('test-vm-1');
        // Will fail until implemented
      });

      it('should return undefined for nonexistent ID', () => {
        const vm = selectVMById(store.getState(), 'nonexistent');
        expect(vm).toBeUndefined();
      });
    });

    describe('selectVMsByPowerState', () => {
      it('should return running VMs', () => {
        const runningVMs = selectVMsByPowerState(store.getState(), 'running');
        expect(runningVMs).toHaveLength(2);
        expect(runningVMs.every(vm => vm.powerState === 'running')).toBe(true);
        // Will fail until implemented
      });

      it('should return deallocated VMs', () => {
        const deallocatedVMs = selectVMsByPowerState(store.getState(), 'deallocated');
        expect(deallocatedVMs).toHaveLength(1);
        expect(deallocatedVMs[0].name).toBe('test-vm-2');
      });

      it('should return empty array for no matches', () => {
        const stoppedVMs = selectVMsByPowerState(store.getState(), 'stopped');
        expect(stoppedVMs).toEqual([]);
      });
    });

    describe('selectIsLoading', () => {
      it('should return loading state', () => {
        expect(selectIsLoading(store.getState())).toBe(false);

        store.dispatch(fetchVMs.pending('', undefined));
        expect(selectIsLoading(store.getState())).toBe(true);
        // Will fail until implemented
      });
    });

    describe('selectError', () => {
      it('should return error state', () => {
        expect(selectError(store.getState())).toBeNull();

        store.dispatch(fetchVMs.rejected(new Error('Test error'), '', undefined));
        expect(selectError(store.getState())).toBeTruthy();
        // Will fail until implemented
      });
    });
  });

  describe('persistence', () => {
    it('should serialize state for storage', () => {
      const mockVMs = [
        {
          id: 'vm-1',
          name: 'test-vm',
          resourceGroup: 'rg-test',
          powerState: 'running',
          size: 'Standard_B2s',
          location: 'eastus',
        },
      ];

      store.dispatch(fetchVMs.fulfilled(mockVMs, '', undefined));

      const state = store.getState().vms;
      const serialized = JSON.stringify(state);

      expect(serialized).toBeTruthy();
      expect(JSON.parse(serialized).items).toEqual(mockVMs);
    });

    it('should handle lastSync as timestamp', () => {
      store.dispatch(fetchVMs.fulfilled([], '', undefined));

      const state = store.getState().vms;
      expect(typeof state.lastSync).toBe('number');
      expect(state.lastSync).toBeGreaterThan(Date.now() - 1000);
    });
  });
});
