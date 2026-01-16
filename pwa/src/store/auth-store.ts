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
import { PublicClientApplication, InteractionRequiredAuthError } from '@azure/msal-browser';
import { TokenStorage } from '../auth/token-storage';

const tokenStorage = new TokenStorage();

// MSAL configuration
const msalConfig = {
  auth: {
    clientId: import.meta.env.VITE_AZURE_CLIENT_ID,
    authority: `https://login.microsoftonline.com/${import.meta.env.VITE_AZURE_TENANT_ID}`,
  },
  cache: {
    cacheLocation: 'localStorage',
    storeAuthStateInCookie: false,
  },
};

// Create MSAL instance
const msalInstance = new PublicClientApplication(msalConfig);

// Initialize MSAL
await msalInstance.initialize();

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
    const accounts = msalInstance.getAllAccounts();

    if (accounts.length === 0) {
      return false;
    }

    try {
      const response = await msalInstance.acquireTokenSilent({
        scopes: ['https://management.azure.com/.default'],
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
 * Interactive authentication (popup or redirect)
 */
export const loginInteractive = createAsyncThunk<void, void>(
  'auth/loginInteractive',
  async () => {
    try {
      const response = await msalInstance.loginPopup({
        scopes: ['https://management.azure.com/.default', 'offline_access'],
      });

      // Save token
      const expiresOn = response.expiresOn?.getTime() || Date.now() + 3600000;
      await tokenStorage.saveTokens(response.accessToken, '', expiresOn);
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
    // Try silent auth first
    const accounts = msalInstance.getAllAccounts();

    if (accounts.length === 0) {
      return false;
    }

    try {
      const response = await msalInstance.acquireTokenSilent({
        scopes: ['https://management.azure.com/.default'],
        account: accounts[0],
      });

      const expiresOn = response.expiresOn?.getTime() || Date.now() + 3600000;
      await tokenStorage.saveTokens(response.accessToken, '', expiresOn);

      return true;
    } catch (error) {
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

export const { clearError } = authSlice.actions;

// Selectors
export const selectIsAuthenticated = (state: { auth: AuthState }) => state.auth.isAuthenticated;
export const selectAuthLoading = (state: { auth: AuthState }) => state.auth.loading;
export const selectAuthError = (state: { auth: AuthState }) => state.auth.error;
export const selectUserEmail = (state: { auth: AuthState }) => state.auth.userEmail;

export default authSlice.reducer;
