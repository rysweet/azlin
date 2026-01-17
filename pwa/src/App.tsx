/**
 * Main App Component for Azlin Mobile PWA
 *
 * Root component with routing and authentication flow.
 *
 * Philosophy:
 * - Single responsibility: App structure and routing
 * - Self-contained with React Router
 * - Zero-BS: Real authentication and routing
 */

import React, { useEffect, useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { useDispatch, useSelector } from 'react-redux';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';
import { PublicClientApplication } from '@azure/msal-browser';
import { AppDispatch } from './store/store';
import { checkAuth, selectIsAuthenticated } from './store/auth-store';
import { TokenStorage } from './auth/token-storage';

// Lazy load pages
const LoginPage = React.lazy(() => import('./pages/LoginPage'));
const DashboardPage = React.lazy(() => import('./pages/DashboardPage'));
const VMListPage = React.lazy(() => import('./pages/VMListPage'));
const VMDetailPage = React.lazy(() => import('./pages/VMDetailPage'));
const TmuxPage = React.lazy(() => import('./pages/TmuxPage'));

const theme = createTheme({
  palette: {
    mode: 'light',
    primary: {
      main: '#0078d4',
    },
    secondary: {
      main: '#005a9e',
    },
  },
});

// Create MSAL instance for redirect handling
const msalConfig = {
  auth: {
    clientId: import.meta.env.VITE_AZURE_CLIENT_ID,
    authority: `https://login.microsoftonline.com/${import.meta.env.VITE_AZURE_TENANT_ID}`,
    redirectUri: window.location.origin,
  },
  cache: {
    cacheLocation: 'localStorage',
    storeAuthStateInCookie: false,
  },
};

const msalInstance = new PublicClientApplication(msalConfig);

function App() {
  const dispatch = useDispatch<AppDispatch>();
  const isAuthenticated = useSelector(selectIsAuthenticated);
  const [msalInitialized, setMsalInitialized] = useState(false);

  useEffect(() => {
    // Initialize MSAL and handle redirect response
    const initMsal = async () => {
      await msalInstance.initialize();

      // Handle redirect response (user returning from Microsoft login)
      const response = await msalInstance.handleRedirectPromise();

      if (response) {
        console.log('🏴‍☠️ Redirect response received:', response);

        // Save token
        const tokenStorage = new TokenStorage();
        const expiresOn = response.expiresOn?.getTime() || Date.now() + 3600000;
        await tokenStorage.saveTokens(response.accessToken, '', expiresOn);

        console.log('🏴‍☠️ Token saved from redirect');
      }

      setMsalInitialized(true);

      // Check if user is already authenticated
      dispatch(checkAuth());
    };

    initMsal();
  }, [dispatch]);

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <BrowserRouter>
        <React.Suspense fallback={<div>Loading...</div>}>
          <Routes>
            <Route
              path="/login"
              element={isAuthenticated ? <Navigate to="/dashboard" /> : <LoginPage />}
            />
            <Route
              path="/dashboard"
              element={isAuthenticated ? <DashboardPage /> : <Navigate to="/login" />}
            />
            <Route
              path="/vms"
              element={isAuthenticated ? <VMListPage /> : <Navigate to="/login" />}
            />
            <Route
              path="/vms/:vmId"
              element={isAuthenticated ? <VMDetailPage /> : <Navigate to="/login" />}
            />
            <Route
              path="/tmux/:vmId/:sessionName"
              element={isAuthenticated ? <TmuxPage /> : <Navigate to="/login" />}
            />
            <Route
              path="/"
              element={<Navigate to={isAuthenticated ? "/dashboard" : "/login"} />}
            />
          </Routes>
        </React.Suspense>
      </BrowserRouter>
    </ThemeProvider>
  );
}

export default App;
