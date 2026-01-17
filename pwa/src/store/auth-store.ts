/**
 * Auth Redux Store for Azlin Mobile PWA
 *
 * State management for Azure AD authentication using MSAL Browser.
 *
 * Philosophy:
 * - Single responsibility: Authentication state
 * - Self-contained with MSAL integration
 * - Zero-BS: Real Azure AD authentication via MSAL
 */

import { createSlice, createAsyncThunk } from '@reduxjs/toolkit';
import { InteractionRequiredAuthError } from '@azure/msal-browser';
import { TokenStorage } from '../auth/token-storage';
import { msalInstance, initializeMsal, AZURE_SCOPES } from '../auth/msal-instance';

const tokenStorage = new TokenStorage();

interface AuthState {
  isAuthenticated: boolean;
  loading: boolean;
  error: string | null;
  userEmail: string | null;
}

const initialState: AuthState = {
  isAuthenticated: false,
  loading: false,
  error: null,
  userEmail: null,
};

/**
 * Silent authentication (try to get token without user interaction)
 */
export const silentAuth = createAsyncThunk<boolean, void>(
  'auth/silent',
  async () => {
    // Ensure MSAL is initialized
    await initializeMsal();

    const accounts = msalInstance.getAllAccounts();

    if (accounts.length === 0) {
      return false;
    }

    try {
      const response = await msalInstance.acquireTokenSilent({
        scopes: AZURE_SCOPES,
        account: accounts[0],
      });

      // Save token
      const expiresOn = response.expiresOn?.getTime() || Date.now() + 3600000;
      await tokenStorage.saveTokens(response.accessToken, '', expiresOn);

      return true;
    } catch (error) {
      if (error instanceof InteractionRequiredAuthError) {
        return false;
      }
      throw error;
    }
  }
);

/**
 * Interactive authentication (using redirect instead of popup)
 */
export const loginInteractive = createAsyncThunk<void, void>(
  'auth/loginInteractive',
  async () => {
    try {
      // Ensure MSAL is initialized
      await initializeMsal();

      // Use redirect flow instead of popup (more reliable, no COOP issues)
      await msalInstance.loginRedirect({
        scopes: AZURE_SCOPES,
      });
      // Note: This function never returns - page redirects
      // handleRedirectPromise() in App.tsx handles the return
    } catch (error) {
      throw new Error(`Login failed: ${error instanceof Error ? error.message : String(error)}`);
    }
  }
);

/**
 * Check if already authenticated
 */
export const checkAuth = createAsyncThunk<boolean, void>(
  'auth/checkAuth',
  async () => {
    // Ensure MSAL is initialized
    await initializeMsal();

    // Try silent auth first
    const accounts = msalInstance.getAllAccounts();
    console.log('checkAuth: Found accounts:', accounts.length);

    if (accounts.length === 0) {
      return false;
    }

    try {
      const response = await msalInstance.acquireTokenSilent({
        scopes: AZURE_SCOPES,
        account: accounts[0],
      });

      const expiresOn = response.expiresOn?.getTime() || Date.now() + 3600000;
      await tokenStorage.saveTokens(response.accessToken, '', expiresOn);
      console.log('checkAuth: Token acquired successfully');

      return true;
    } catch (error) {
      console.log('checkAuth: Silent auth failed:', error);
      return false;
    }
  }
);

/**
 * Logout (clear tokens)
 */
export const logout = createAsyncThunk<void, void>(
  'auth/logout',
  async () => {
    // Ensure MSAL is initialized
    await initializeMsal();

    const accounts = msalInstance.getAllAccounts();

    if (accounts.length > 0) {
      await msalInstance.logoutPopup({
        account: accounts[0],
      });
    }

    await tokenStorage.clearTokens();
  }
);

/**
 * Get current user email
 */
function getUserEmail(): string | null {
  const accounts = msalInstance.getAllAccounts();
  return accounts.length > 0 ? accounts[0].username : null;
}

const authSlice = createSlice({
  name: 'auth',
  initialState,
  reducers: {
    clearError: (state) => {
      state.error = null;
    },
    setAuthenticated: (state, action) => {
      state.isAuthenticated = action.payload;
      state.userEmail = getUserEmail();
    },
  },
  extraReducers: (builder) => {
    // silentAuth
    builder
      .addCase(silentAuth.pending, (state) => {
        state.loading = true;
      })
      .addCase(silentAuth.fulfilled, (state, action) => {
        state.isAuthenticated = action.payload;
        state.loading = false;
        state.userEmail = getUserEmail();
      })
      .addCase(silentAuth.rejected, (state, action) => {
        state.loading = false;
        state.error = action.error.message || 'Authentication check failed';
      });

    // loginInteractive
    builder
      .addCase(loginInteractive.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(loginInteractive.fulfilled, (state) => {
        state.isAuthenticated = true;
        state.loading = false;
        state.userEmail = getUserEmail();
      })
      .addCase(loginInteractive.rejected, (state, action) => {
        state.loading = false;
        state.error = action.error.message || 'Login failed';
      });

    // checkAuth
    builder
      .addCase(checkAuth.fulfilled, (state, action) => {
        state.isAuthenticated = action.payload;
        state.userEmail = getUserEmail();
      });

    // logout
    builder
      .addCase(logout.fulfilled, (state) => {
        state.isAuthenticated = false;
        state.userEmail = null;
        state.error = null;
      });
  },
});

export const { clearError, setAuthenticated } = authSlice.actions;

// Selectors
export const selectIsAuthenticated = (state: { auth: AuthState }) => state.auth.isAuthenticated;
export const selectAuthLoading = (state: { auth: AuthState }) => state.auth.loading;
export const selectAuthError = (state: { auth: AuthState }) => state.auth.error;
export const selectUserEmail = (state: { auth: AuthState }) => state.auth.userEmail;

export default authSlice.reducer;
