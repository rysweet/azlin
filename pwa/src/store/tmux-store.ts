/**
 * Tmux Redux Store for Azlin Mobile PWA
 *
 * State management for tmux sessions and snapshots.
 *
 * Philosophy:
 * - Single responsibility: Tmux session state
 * - Self-contained with TmuxApi integration
 * - Zero-BS: Real tmux commands via Azure Run Command API
 */

import { createSlice, createAsyncThunk, PayloadAction } from '@reduxjs/toolkit';
import { TmuxApi, TmuxSession, TmuxSnapshot } from '../tmux/tmux-api';
import { AzureClient, PollingProgress } from '../api/azure-client';

interface TmuxState {
  sessions: Record<string, TmuxSession[]>; // Keyed by vmId
  snapshots: Record<string, TmuxSnapshot>; // Keyed by vmId:sessionName
  loading: boolean;
  error: string | null;
  pollingProgress: PollingProgress | null; // Track polling status for UI
}

const initialState: TmuxState = {
  sessions: {},
  snapshots: {},
  loading: false,
  error: null,
  pollingProgress: null,
};

const getTmuxApi = () => {
  const subscriptionId = import.meta.env.VITE_AZURE_SUBSCRIPTION_ID;
  const azureClient = new AzureClient(subscriptionId);
  return new TmuxApi(azureClient);
};

/**
 * Fetch sessions for a VM
 */
export const fetchSessions = createAsyncThunk<
  { vmId: string; sessions: TmuxSession[] },
  { resourceGroup: string; vmName: string },
  { dispatch: any }
>(
  'tmux/fetchSessions',
  async ({ resourceGroup, vmName }, { dispatch }) => {
    const tmuxApi = getTmuxApi();

    // Callback to update polling progress in the store
    const onProgress = (progress: PollingProgress) => {
      dispatch(setPollingProgress(progress));
    };

    const sessions = await tmuxApi.listSessions(resourceGroup, vmName, onProgress);
    const vmId = `${resourceGroup}/${vmName}`;

    // Clear polling progress when done
    dispatch(setPollingProgress(null));

    return { vmId, sessions };
  }
);

/**
 * Capture session snapshot
 */
export const captureSnapshot = createAsyncThunk<
  { snapshotId: string; snapshot: TmuxSnapshot },
  { resourceGroup: string; vmName: string; sessionName: string }
>(
  'tmux/captureSnapshot',
  async ({ resourceGroup, vmName, sessionName }) => {
    const tmuxApi = getTmuxApi();
    const snapshot = await tmuxApi.captureSnapshot(resourceGroup, vmName, sessionName);
    const snapshotId = `${resourceGroup}/${vmName}:${sessionName}`;
    return { snapshotId, snapshot };
  }
);

/**
 * Send keys to session
 */
export const sendKeys = createAsyncThunk<
  void,
  { resourceGroup: string; vmName: string; sessionName: string; keys: string }
>(
  'tmux/sendKeys',
  async ({ resourceGroup, vmName, sessionName, keys }) => {
    const tmuxApi = getTmuxApi();
    await tmuxApi.sendKeys(resourceGroup, vmName, sessionName, keys);
  }
);

const tmuxSlice = createSlice({
  name: 'tmux',
  initialState,
  reducers: {
    clearSnapshots: (state) => {
      state.snapshots = {};
    },
    setPollingProgress: (state, action: PayloadAction<PollingProgress | null>) => {
      state.pollingProgress = action.payload;
    },
  },
  extraReducers: (builder) => {
    // fetchSessions
    builder
      .addCase(fetchSessions.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(fetchSessions.fulfilled, (state, action) => {
        state.sessions[action.payload.vmId] = action.payload.sessions;
        state.loading = false;
      })
      .addCase(fetchSessions.rejected, (state, action) => {
        state.loading = false;
        state.error = action.error.message || 'Failed to fetch sessions';
      });

    // captureSnapshot
    builder
      .addCase(captureSnapshot.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(captureSnapshot.fulfilled, (state, action) => {
        state.snapshots[action.payload.snapshotId] = action.payload.snapshot;
        state.loading = false;
      })
      .addCase(captureSnapshot.rejected, (state, action) => {
        state.loading = false;
        state.error = action.error.message || 'Failed to capture snapshot';
      });

    // sendKeys
    builder
      .addCase(sendKeys.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(sendKeys.fulfilled, (state) => {
        state.loading = false;
      })
      .addCase(sendKeys.rejected, (state, action) => {
        state.loading = false;
        state.error = action.error.message || 'Failed to send keys';
      });
  },
});

export const { clearSnapshots, setPollingProgress } = tmuxSlice.actions;

// Selectors
export const selectSessionsByVmId = (state: { tmux: TmuxState }, vmId: string) =>
  state.tmux.sessions[vmId] || [];

export const selectSnapshotById = (state: { tmux: TmuxState }, snapshotId: string) =>
  state.tmux.snapshots[snapshotId];

export const selectTmuxLoading = (state: { tmux: TmuxState }) => state.tmux.loading;

export const selectTmuxError = (state: { tmux: TmuxState }) => state.tmux.error;

export const selectPollingProgress = (state: { tmux: TmuxState }) => state.tmux.pollingProgress;

export default tmuxSlice.reducer;
