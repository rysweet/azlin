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
import { AppDispatch } from './store/store';
import { checkAuth, selectIsAuthenticated, setAuthenticated } from './store/auth-store';
import { TokenStorage } from './auth/token-storage';
import { msalInstance, initializeMsal } from './auth/msal-instance';

// Lazy load pages
const LoginPage = React.lazy(() => import('./pages/LoginPage'));
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

function App() {
  const dispatch = useDispatch<AppDispatch>();
  const isAuthenticated = useSelector(selectIsAuthenticated);
  const [isInitializing, setIsInitializing] = useState(true);

  useEffect(() => {
    // Initialize MSAL and handle redirect response
    const initMsal = async () => {
      // Use shared MSAL instance (single source of truth)
      await initializeMsal();

      // Handle redirect response (user returning from Microsoft login)
      const response = await msalInstance.handleRedirectPromise();

      if (response) {
        console.log('🏴‍☠️ Redirect response received:', response);
        console.log('🏴‍☠️ Account:', response.account?.username);

        // Save token
        const tokenStorage = new TokenStorage();
        const expiresOn = response.expiresOn?.getTime() || Date.now() + 3600000;
        await tokenStorage.saveTokens(response.accessToken, '', expiresOn);

        console.log('🏴‍☠️ Token saved from redirect');

        // CRITICAL: Set authenticated state in Redux
        dispatch(setAuthenticated(true));
        console.log('🏴‍☠️ Redux auth state set to authenticated');
      } else {
        console.log('🏴‍☠️ No redirect response - checking existing auth');
        // Only check auth if no redirect response (to avoid race condition)
        dispatch(checkAuth());
      }

      setIsInitializing(false);
    };

    initMsal();
  }, [dispatch]);

  // Show loading while MSAL initializes to avoid flash of login page
  if (isInitializing) {
    return (
      <ThemeProvider theme={theme}>
        <CssBaseline />
        <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100vh' }}>
          Loading...
        </div>
      </ThemeProvider>
    );
  }

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      <BrowserRouter>
        <React.Suspense fallback={<div>Loading...</div>}>
          <Routes>
            <Route
              path="/login"
              element={isAuthenticated ? <Navigate to="/" /> : <LoginPage />}
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
              element={isAuthenticated ? <VMListPage /> : <Navigate to="/login" />}
            />
          </Routes>
        </React.Suspense>
      </BrowserRouter>
    </ThemeProvider>
  );
}

export default App;
