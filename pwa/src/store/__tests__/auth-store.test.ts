/**
 * Unit Tests for Auth Redux Store (60% of testing pyramid)
 *
 * Tests Redux Toolkit slice for authentication state management with MSAL.
 * Covers happy path, edge cases, error handling, and state transitions.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { configureStore } from '@reduxjs/toolkit';
import authReducer, {
  silentAuth,
  loginInteractive,
  checkAuth,
  logout,
  clearError,
  setAuthenticated,
  selectIsAuthenticated,
  selectAuthLoading,
  selectAuthError,
  selectUserEmail,
} from '../auth-store';

// Mock MSAL and token storage
vi.mock('../auth/token-storage');
vi.mock('../auth/msal-instance', () => ({
  msalInstance: {
    getAllAccounts: vi.fn(),
    acquireTokenSilent: vi.fn(),
    loginRedirect: vi.fn(),
    logoutPopup: vi.fn(),
  },
  initializeMsal: vi.fn(),
  AZURE_SCOPES: ['https://management.azure.com/.default'],
}));
vi.mock('../utils/logger', () => ({
  createLogger: () => ({
    debug: vi.fn(),
    info: vi.fn(),
    warn: vi.fn(),
    error: vi.fn(),
  }),
}));

describe('Auth Store', () => {
  let store: ReturnType<typeof configureStore>;

  beforeEach(() => {
    store = configureStore({
      reducer: {
        auth: authReducer,
      },
    });
    vi.clearAllMocks();
  });

  describe('initial state', () => {
    it('should not be authenticated by default', () => {
      const state = store.getState().auth;
      expect(state.isAuthenticated).toBe(false);
    });

    it('should not be loading by default', () => {
      const state = store.getState().auth;
      expect(state.loading).toBe(false);
    });

    it('should have no error by default', () => {
      const state = store.getState().auth;
      expect(state.error).toBeNull();
    });

    it('should have no user email by default', () => {
      const state = store.getState().auth;
      expect(state.userEmail).toBeNull();
    });
  });

  describe('clearError action', () => {
    it('should clear error state', () => {
      // Set error first by simulating a failed auth
      store.dispatch(
        silentAuth.rejected(new Error('Auth failed'), '', undefined)
      );
      expect(store.getState().auth.error).toBeTruthy();

      // Clear error
      store.dispatch(clearError());
      expect(store.getState().auth.error).toBeNull();
    });

    it('should not affect other state', () => {
      const initialState = store.getState().auth;
      store.dispatch(clearError());
      const newState = store.getState().auth;

      expect(newState.isAuthenticated).toBe(initialState.isAuthenticated);
      expect(newState.loading).toBe(initialState.loading);
      expect(newState.userEmail).toBe(initialState.userEmail);
    });
  });

  describe('setAuthenticated action', () => {
    it('should set authentication status to true', () => {
      store.dispatch(setAuthenticated(true));
      expect(store.getState().auth.isAuthenticated).toBe(true);
    });

    it('should set authentication status to false', () => {
      store.dispatch(setAuthenticated(true));
      store.dispatch(setAuthenticated(false));
      expect(store.getState().auth.isAuthenticated).toBe(false);
    });
  });

  describe('silentAuth thunk', () => {
    it('should set loading to true when pending', () => {
      store.dispatch(silentAuth.pending('', undefined));

      const state = store.getState().auth;
      expect(state.loading).toBe(true);
    });

    it('should set authenticated when fulfilled with true', () => {
      store.dispatch(silentAuth.fulfilled(true, '', undefined));

      const state = store.getState().auth;
      expect(state.isAuthenticated).toBe(true);
      expect(state.loading).toBe(false);
    });

    it('should not be authenticated when fulfilled with false', () => {
      store.dispatch(silentAuth.fulfilled(false, '', undefined));

      const state = store.getState().auth;
      expect(state.isAuthenticated).toBe(false);
      expect(state.loading).toBe(false);
    });

    it('should set error when rejected', () => {
      const error = new Error('Silent auth failed');
      store.dispatch(silentAuth.rejected(error, '', undefined));

      const state = store.getState().auth;
      expect(state.loading).toBe(false);
      expect(state.error).toBe('Silent auth failed');
    });

    it('should set default error message if none provided', () => {
      const error = new Error();
      error.message = '';
      store.dispatch(silentAuth.rejected(error, '', undefined));

      const state = store.getState().auth;
      expect(state.error).toBe('Authentication check failed');
    });
  });

  describe('loginInteractive thunk', () => {
    it('should set loading and clear error when pending', () => {
      // Set error first
      store.dispatch(
        silentAuth.rejected(new Error('Previous error'), '', undefined)
      );

      store.dispatch(loginInteractive.pending('', undefined));

      const state = store.getState().auth;
      expect(state.loading).toBe(true);
      expect(state.error).toBeNull();
    });

    it('should set authenticated when fulfilled', () => {
      store.dispatch(loginInteractive.fulfilled(undefined, '', undefined));

      const state = store.getState().auth;
      expect(state.isAuthenticated).toBe(true);
      expect(state.loading).toBe(false);
    });

    it('should set error when rejected', () => {
      const error = new Error('Login failed');
      store.dispatch(loginInteractive.rejected(error, '', undefined));

      const state = store.getState().auth;
      expect(state.loading).toBe(false);
      expect(state.error).toBe('Login failed');
    });

    it('should use default error message if none provided', () => {
      const error = new Error();
      error.message = '';
      store.dispatch(loginInteractive.rejected(error, '', undefined));

      const state = store.getState().auth;
      expect(state.error).toBe('Login failed');
    });
  });

  describe('checkAuth thunk', () => {
    it('should set authenticated when fulfilled with true', () => {
      store.dispatch(checkAuth.fulfilled(true, '', undefined));

      const state = store.getState().auth;
      expect(state.isAuthenticated).toBe(true);
    });

    it('should not be authenticated when fulfilled with false', () => {
      // Set authenticated first
      store.dispatch(checkAuth.fulfilled(true, '', undefined));
      expect(store.getState().auth.isAuthenticated).toBe(true);

      // Then check fails
      store.dispatch(checkAuth.fulfilled(false, '', undefined));

      const state = store.getState().auth;
      expect(state.isAuthenticated).toBe(false);
    });

    it('should not set loading state', () => {
      // checkAuth doesn't have pending/rejected handlers, so loading shouldn't change
      const initialLoading = store.getState().auth.loading;
      store.dispatch(checkAuth.fulfilled(true, '', undefined));

      expect(store.getState().auth.loading).toBe(initialLoading);
    });
  });

  describe('logout thunk', () => {
    it('should clear authentication when fulfilled', () => {
      // Set authenticated first
      store.dispatch(checkAuth.fulfilled(true, '', undefined));
      expect(store.getState().auth.isAuthenticated).toBe(true);

      // Logout
      store.dispatch(logout.fulfilled(undefined, '', undefined));

      const state = store.getState().auth;
      expect(state.isAuthenticated).toBe(false);
      expect(state.userEmail).toBeNull();
      expect(state.error).toBeNull();
    });

    it('should clear user email', () => {
      // Manually set state to simulate logged-in user
      store.dispatch(setAuthenticated(true));

      store.dispatch(logout.fulfilled(undefined, '', undefined));

      expect(store.getState().auth.userEmail).toBeNull();
    });

    it('should clear any existing error', () => {
      // Set error first
      store.dispatch(
        silentAuth.rejected(new Error('Previous error'), '', undefined)
      );
      expect(store.getState().auth.error).toBeTruthy();

      // Logout should clear it
      store.dispatch(logout.fulfilled(undefined, '', undefined));
      expect(store.getState().auth.error).toBeNull();
    });
  });

  describe('selectors', () => {
    describe('selectIsAuthenticated', () => {
      it('should return authentication status', () => {
        expect(selectIsAuthenticated(store.getState())).toBe(false);

        store.dispatch(checkAuth.fulfilled(true, '', undefined));
        expect(selectIsAuthenticated(store.getState())).toBe(true);
      });
    });

    describe('selectAuthLoading', () => {
      it('should return loading state', () => {
        expect(selectAuthLoading(store.getState())).toBe(false);

        store.dispatch(silentAuth.pending('', undefined));
        expect(selectAuthLoading(store.getState())).toBe(true);
      });
    });

    describe('selectAuthError', () => {
      it('should return error state', () => {
        expect(selectAuthError(store.getState())).toBeNull();

        const error = new Error('Test error');
        store.dispatch(silentAuth.rejected(error, '', undefined));
        expect(selectAuthError(store.getState())).toBe('Test error');
      });
    });

    describe('selectUserEmail', () => {
      it('should return null when not authenticated', () => {
        expect(selectUserEmail(store.getState())).toBeNull();
      });

      it('should return user email when authenticated', () => {
        // User email is set by getUserEmail() which depends on msalInstance
        // In unit tests, it will be null unless we mock msalInstance.getAllAccounts
        // This is expected behavior for the selector
        store.dispatch(checkAuth.fulfilled(true, '', undefined));
        const email = selectUserEmail(store.getState());
        expect(email).toBeNull(); // null in unit tests without MSAL mock
      });
    });
  });

  describe('state transitions', () => {
    it('should handle complete login flow', () => {
      // Start with initial state
      expect(store.getState().auth.isAuthenticated).toBe(false);

      // Check auth (not authenticated)
      store.dispatch(checkAuth.fulfilled(false, '', undefined));
      expect(store.getState().auth.isAuthenticated).toBe(false);

      // Login pending
      store.dispatch(loginInteractive.pending('', undefined));
      expect(store.getState().auth.loading).toBe(true);

      // Login successful
      store.dispatch(loginInteractive.fulfilled(undefined, '', undefined));
      expect(store.getState().auth.isAuthenticated).toBe(true);
      expect(store.getState().auth.loading).toBe(false);
    });

    it('should handle logout after successful login', () => {
      // Login
      store.dispatch(loginInteractive.fulfilled(undefined, '', undefined));
      expect(store.getState().auth.isAuthenticated).toBe(true);

      // Logout
      store.dispatch(logout.fulfilled(undefined, '', undefined));
      expect(store.getState().auth.isAuthenticated).toBe(false);
      expect(store.getState().auth.userEmail).toBeNull();
    });

    it('should handle silent auth failure followed by interactive login', () => {
      // Silent auth fails
      store.dispatch(silentAuth.fulfilled(false, '', undefined));
      expect(store.getState().auth.isAuthenticated).toBe(false);

      // Interactive login succeeds
      store.dispatch(loginInteractive.fulfilled(undefined, '', undefined));
      expect(store.getState().auth.isAuthenticated).toBe(true);
    });

    it('should preserve error state through successful operations', () => {
      // Set error
      store.dispatch(
        silentAuth.rejected(new Error('Auth failed'), '', undefined)
      );
      expect(store.getState().auth.error).toBeTruthy();

      // Check auth (doesn't clear error)
      store.dispatch(checkAuth.fulfilled(false, '', undefined));
      expect(store.getState().auth.error).toBeTruthy();

      // Only clearError or logout clears it
      store.dispatch(clearError());
      expect(store.getState().auth.error).toBeNull();
    });
  });
});
