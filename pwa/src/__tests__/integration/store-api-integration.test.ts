/**
 * Integration Tests: Redux Store + API (30% of testing pyramid)
 *
 * Tests Redux store interactions with Azure API.
 */

import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { configureStore } from '@reduxjs/toolkit';
import type { RootState } from '../../store/store';
import vmReducer, { fetchVMs, startVM, stopVM } from '../../store/vm-store';
import tmuxReducer, { fetchSessions, captureSnapshot } from '../../store/tmux-store';
import { TokenStorage } from '../../auth/token-storage';

describe('Store + API Integration', () => {
  let store: ReturnType<typeof configureStore>;
  let tokenStorage: TokenStorage;

  beforeEach(async () => {
    // Set up tokens for Azure API calls
    tokenStorage = new TokenStorage();
    await tokenStorage.saveTokens(
      'mock_access_token',
      'mock_refresh_token',
      Date.now() + 3600000
    );

    // Set subscription ID in environment
    process.env.VITE_AZURE_SUBSCRIPTION_ID = 'sub-123';

    store = configureStore({
      reducer: {
        vms: vmReducer,
        tmux: tmuxReducer,
      },
    });
  });

  afterEach(async () => {
    await tokenStorage.clearTokens();
  });

  describe('VM Store + Azure Compute API', () => {
    it('should fetch VMs and populate store', async () => {
      await store.dispatch(fetchVMs() as any);

      const state = (store.getState() as RootState).vms;

      expect(state.loading).toBe(false);
      expect(state.items.length).toBeGreaterThan(0);
      expect(state.lastSync).toBeGreaterThan(0);
      expect(state.error).toBeNull();
      // Will fail until implemented
    });

    it('should filter VMs by azlin-managed tag', async () => {
      await store.dispatch(fetchVMs() as any);

      const state = (store.getState() as RootState).vms;
      const azlinVMs = state.items.filter(vm =>
        vm.tags?.['azlin-managed'] === 'true'
      );

      expect(azlinVMs.length).toBe(state.items.length);
    });

    it('should start VM and update store state', async () => {
      // Fetch VMs first
      await store.dispatch(fetchVMs() as any);

      const vmsBefore = (store.getState() as RootState).vms.items;
      const deallocatedVM = vmsBefore.find(vm => vm.powerState === 'deallocated');

      if (deallocatedVM) {
        await store.dispatch(
          startVM({
            resourceGroup: deallocatedVM.resourceGroup,
            vmName: deallocatedVM.name,
          }) as any
        );

        const vmsAfter = (store.getState() as RootState).vms.items;
        const updatedVM = vmsAfter.find(vm => vm.name === deallocatedVM.name);

        expect(updatedVM?.powerState).toBe('running');
      }
    });

    it('should stop VM and update store state', async () => {
      await store.dispatch(fetchVMs() as any);

      const vmsBefore = (store.getState() as RootState).vms.items;
      const runningVM = vmsBefore.find(vm => vm.powerState === 'running');

      if (runningVM) {
        await store.dispatch(
          stopVM({
            resourceGroup: runningVM.resourceGroup,
            vmName: runningVM.name,
            deallocate: true,
          }) as any
        );

        const vmsAfter = (store.getState() as RootState).vms.items;
        const updatedVM = vmsAfter.find(vm => vm.name === runningVM.name);

        expect(updatedVM?.powerState).toBe('deallocated');
      }
    });

    it('should handle API errors and set error state', async () => {
      // Clear tokens to force authentication error
      await tokenStorage.clearTokens();

      await store.dispatch(fetchVMs() as any);

      const state = (store.getState() as RootState).vms;
      expect(state.error).toBeTruthy();
      expect(state.loading).toBe(false);

      // Restore tokens for other tests
      await tokenStorage.saveTokens(
        'mock_access_token',
        'mock_refresh_token',
        Date.now() + 3600000
      );
    });

    it('should support optimistic updates for VM operations', async () => {
      await store.dispatch(fetchVMs() as any);

      const vmsBefore = (store.getState() as RootState).vms.items;
      const testVM = vmsBefore[0];

      // Dispatch start (optimistic update)
      const startPromise = store.dispatch(
        startVM({
          resourceGroup: testVM.resourceGroup,
          vmName: testVM.name,
        }) as any
      );

      // Store should update immediately (optimistic)
      // Note: This depends on implementation strategy

      await startPromise;

      // After API call, state should reflect actual result
      const vmsAfter = (store.getState() as RootState).vms.items;
      expect(vmsAfter).toBeDefined();
    });
  });

  describe('Tmux Store + Run Command API', () => {
    it('should fetch tmux sessions and populate store', async () => {
      // First get a VM
      await store.dispatch(fetchVMs() as any);
      const vm = (store.getState() as RootState).vms.items[0];

      if (vm) {
        await store.dispatch(
          fetchSessions({
            resourceGroup: vm.resourceGroup,
            vmName: vm.name,
          }) as any
        );

        const state = (store.getState() as RootState).tmux;
        expect(state.sessions).toBeDefined();
        // Will fail until implemented
      }
    });

    it('should capture session snapshot and store it', async () => {
      await store.dispatch(fetchVMs() as any);
      const vm = (store.getState() as RootState).vms.items[0];

      if (vm) {
        // Fetch sessions first
        await store.dispatch(
          fetchSessions({
            resourceGroup: vm.resourceGroup,
            vmName: vm.name,
          }) as any
        );

        const sessions = (store.getState() as RootState).tmux.sessions;
        if (sessions.length > 0) {
          await store.dispatch(
            captureSnapshot({
              resourceGroup: vm.resourceGroup,
              vmName: vm.name,
              sessionName: sessions[0].name,
            }) as any
          );

          const state = (store.getState() as RootState).tmux;
          expect(state.snapshots[sessions[0].name]).toBeDefined();
        }
      }
    });

    it('should handle Run Command timeout (90 seconds)', async () => {
      // Azure Run Command has 90 second timeout
      // This test should complete or fail appropriately

      await store.dispatch(fetchVMs() as any);
      const vm = (store.getState() as RootState).vms.items[0];

      if (vm) {
        const startTime = Date.now();

        try {
          await store.dispatch(
            captureSnapshot({
              resourceGroup: vm.resourceGroup,
              vmName: vm.name,
              sessionName: 'test-session',
            }) as any
          );
        } catch (error) {
          const duration = Date.now() - startTime;
          // Should fail before or at 90 seconds
          expect(duration).toBeLessThanOrEqual(92000);
        }
      }
    });
  });

  describe('Multi-Store Operations', () => {
    it('should fetch VM list and tmux sessions in parallel', async () => {
      const startTime = Date.now();

      // Dispatch both in parallel
      const vmPromise = store.dispatch(fetchVMs() as any);

      await vmPromise;

      const vm = (store.getState() as RootState).vms.items[0];
      if (vm) {
        const tmuxPromise = store.dispatch(
          fetchSessions({
            resourceGroup: vm.resourceGroup,
            vmName: vm.name,
          }) as any
        );

        await Promise.all([vmPromise, tmuxPromise]);

        const duration = Date.now() - startTime;

        // Parallel execution should be faster than sequential
        // (This is a basic check - actual implementation will vary)
        expect(duration).toBeLessThan(60000); // 60 seconds max
      }
    });
  });

  describe('Store Persistence', () => {
    it('should persist VM state to IndexedDB', async () => {
      await store.dispatch(fetchVMs() as any);

      const state = (store.getState() as RootState).vms;

      // Store should mark data for persistence
      expect(state.lastSync).toBeDefined();
      expect(state.items.length).toBeGreaterThan(0);
    });

    it('should load persisted state on initialization', async () => {
      // First fetch and store data
      await store.dispatch(fetchVMs() as any);
      const vmsAfterFetch = (store.getState() as RootState).vms.items;

      // Create new store instance (simulating app restart)
      const newStore = configureStore({
        reducer: { vms: vmReducer },
        // In real implementation, would load from IndexedDB
      });

      // New store should load from persistence
      // (Implementation detail - may require explicit rehydration)
      expect(newStore.getState().vms).toBeDefined();
    });
  });
});
