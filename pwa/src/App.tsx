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

import React, { useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { useDispatch, useSelector } from 'react-redux';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';
import { AppDispatch } from './store/store';
import { checkAuth, selectIsAuthenticated } from './store/auth-store';

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

function App() {
  const dispatch = useDispatch<AppDispatch>();
  const isAuthenticated = useSelector(selectIsAuthenticated);

  useEffect(() => {
    // Check if user is already authenticated
    dispatch(checkAuth());
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
