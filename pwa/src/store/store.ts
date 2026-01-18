/**
 * Redux Store Configuration for Azlin Mobile PWA
 *
 * Combines all Redux slices into a single store.
 *
 * Philosophy:
 * - Single responsibility: Store configuration
 * - Self-contained with all reducers
 * - Zero-BS: Real Redux Toolkit store
 */

import { configureStore } from '@reduxjs/toolkit';
import vmReducer from './vm-store';
import authReducer from './auth-store';
import tmuxReducer from './tmux-store';

export const store = configureStore({
  reducer: {
    vms: vmReducer,
    auth: authReducer,
    tmux: tmuxReducer,
  },
  middleware: (getDefaultMiddleware) =>
    getDefaultMiddleware({
      serializableCheck: {
        // Ignore these paths in state for serialization checks
        ignoredPaths: ['tmux.sessions', 'tmux.snapshots'],
      },
    }),
});

// Export types
export type RootState = ReturnType<typeof store.getState>;
export type AppDispatch = typeof store.dispatch;

// Export store instance
export default store;
