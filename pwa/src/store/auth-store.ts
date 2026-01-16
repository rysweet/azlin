/**
 * Auth Redux Store for Azlin Mobile PWA
 *
 * State management for Azure AD authentication using device code flow.
 *
 * Philosophy:
 * - Single responsibility: Authentication state
 * - Self-contained with TokenStorage integration
 * - Zero-BS: Real Azure AD OAuth2 device code flow
 */

import { createSlice, createAsyncThunk } from '@reduxjs/toolkit';
import { TokenStorage } from '../auth/token-storage';

const AZURE_DEVICE_CODE_URL = 'https://login.microsoftonline.com/common/oauth2/v2.0/devicecode';
const AZURE_TOKEN_URL = 'https://login.microsoftonline.com/common/oauth2/v2.0/token';

interface DeviceCodeResponse {
  device_code: string;
  user_code: string;
  verification_uri: string;
  expires_in: number;
  interval: number;
  message: string;
}

interface AuthState {
  isAuthenticated: boolean;
  loading: boolean;
  error: string | null;
  deviceCode: DeviceCodeResponse | null;
  pollingIntervalId: number | null;
}

const initialState: AuthState = {
  isAuthenticated: false,
  loading: false,
  error: null,
  deviceCode: null,
  pollingIntervalId: null,
};

const tokenStorage = new TokenStorage();

/**
 * Initiate device code flow
 */
export const initiateDeviceCodeAuth = createAsyncThunk<DeviceCodeResponse, void>(
  'auth/initiateDeviceCode',
  async () => {
    const clientId = import.meta.env.VITE_AZURE_CLIENT_ID;

    const response = await fetch(AZURE_DEVICE_CODE_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: new URLSearchParams({
        client_id: clientId,
        scope: 'https://management.azure.com/.default offline_access',
      }),
    });

    if (!response.ok) {
      throw new Error('Failed to initiate device code flow');
    }

    return await response.json();
  }
);

/**
 * Poll for token using device code
 */
export const pollForToken = createAsyncThunk<void, string>(
  'auth/pollToken',
  async (deviceCode) => {
    const clientId = import.meta.env.VITE_AZURE_CLIENT_ID;

    const response = await fetch(AZURE_TOKEN_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: new URLSearchParams({
        client_id: clientId,
        grant_type: 'urn:ietf:params:oauth:grant-type:device_code',
        device_code: deviceCode,
      }),
    });

    if (!response.ok) {
      const error = await response.json();
      if (error.error === 'authorization_pending') {
        throw new Error('authorization_pending');
      }
      throw new Error(error.error_description || 'Token polling failed');
    }

    const data = await response.json();

    // Save tokens
    const expiresOn = Date.now() + (data.expires_in * 1000);
    await tokenStorage.saveTokens(data.access_token, data.refresh_token, expiresOn);
  }
);

/**
 * Check if already authenticated
 */
export const checkAuth = createAsyncThunk<boolean, void>(
  'auth/checkAuth',
  async () => {
    return await tokenStorage.isAuthenticated();
  }
);

/**
 * Logout (clear tokens)
 */
export const logout = createAsyncThunk<void, void>(
  'auth/logout',
  async () => {
    await tokenStorage.clearTokens();
  }
);

const authSlice = createSlice({
  name: 'auth',
  initialState,
  reducers: {
    clearDeviceCode: (state) => {
      state.deviceCode = null;
      state.error = null;
    },
  },
  extraReducers: (builder) => {
    // initiateDeviceCodeAuth
    builder
      .addCase(initiateDeviceCodeAuth.pending, (state) => {
        state.loading = true;
        state.error = null;
      })
      .addCase(initiateDeviceCodeAuth.fulfilled, (state, action) => {
        state.deviceCode = action.payload;
        state.loading = false;
      })
      .addCase(initiateDeviceCodeAuth.rejected, (state, action) => {
        state.loading = false;
        state.error = action.error.message || 'Failed to initiate authentication';
      });

    // pollForToken
    builder
      .addCase(pollForToken.fulfilled, (state) => {
        state.isAuthenticated = true;
        state.deviceCode = null;
        state.error = null;
      })
      .addCase(pollForToken.rejected, (state, action) => {
        // Don't set error for authorization_pending (expected during polling)
        if (action.error.message !== 'authorization_pending') {
          state.error = action.error.message || 'Authentication failed';
        }
      });

    // checkAuth
    builder
      .addCase(checkAuth.fulfilled, (state, action) => {
        state.isAuthenticated = action.payload;
      });

    // logout
    builder
      .addCase(logout.fulfilled, (state) => {
        state.isAuthenticated = false;
        state.deviceCode = null;
        state.error = null;
      });
  },
});

export const { clearDeviceCode } = authSlice.actions;

// Selectors
export const selectIsAuthenticated = (state: { auth: AuthState }) => state.auth.isAuthenticated;
export const selectDeviceCode = (state: { auth: AuthState }) => state.auth.deviceCode;
export const selectAuthLoading = (state: { auth: AuthState }) => state.auth.loading;
export const selectAuthError = (state: { auth: AuthState }) => state.auth.error;

export default authSlice.reducer;
