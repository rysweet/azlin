import React from 'react';
import ReactDOM from 'react-dom/client';
import { Provider } from 'react-redux';
import App from './App';
import store from './store/store';
import './index.css';
import { validateEnv } from './config/env-validation';

// Validate environment variables at startup
// Fails fast with clear error message if any required vars are missing
try {
  validateEnv();
} catch (error) {
  // Show error in console and DOM for development
  console.error('Environment validation failed:', error);

  const root = document.getElementById('root');
  if (root) {
    root.innerHTML = `
      <div style="padding: 20px; font-family: monospace; color: #d00;">
        <h1>Configuration Error</h1>
        <pre>${error instanceof Error ? error.message : String(error)}</pre>
      </div>
    `;
  }

  throw error;
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <Provider store={store}>
      <App />
    </Provider>
  </React.StrictMode>
);
