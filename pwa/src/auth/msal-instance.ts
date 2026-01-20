/**
 * Shared MSAL Instance for Azlin Mobile PWA
 *
 * Single source of truth for MSAL configuration and instance.
 * All auth operations must use this shared instance to ensure
 * consistent state across the application.
 *
 * Philosophy:
 * - Single responsibility: MSAL configuration and instance
 * - Self-contained: No dependencies except MSAL
 * - Zero-BS: Real Azure AD authentication
 */

import { PublicClientApplication, Configuration } from '@azure/msal-browser';
import { createLogger } from '../utils/logger';

const logger = createLogger('[MSAL]');

// MSAL configuration
const msalConfig: Configuration = {
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

// Create single shared MSAL instance
export const msalInstance = new PublicClientApplication(msalConfig);

// Track initialization state
let isInitialized = false;
let initPromise: Promise<void> | null = null;

/**
 * Initialize MSAL instance (idempotent - safe to call multiple times)
 */
export async function initializeMsal(): Promise<void> {
  if (isInitialized) {
    return;
  }

  if (initPromise) {
    return initPromise;
  }

  initPromise = msalInstance.initialize().then(() => {
    isInitialized = true;
    logger.info('MSAL instance initialized');
  });

  return initPromise;
}

/**
 * Check if MSAL is initialized
 */
export function isMsalInitialized(): boolean {
  return isInitialized;
}

// Azure Management API scopes
export const AZURE_SCOPES = ['https://management.azure.com/.default', 'offline_access'];
