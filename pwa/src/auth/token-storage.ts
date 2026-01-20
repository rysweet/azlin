/**
 * Token Storage for Azlin Mobile PWA
 *
 * Secure token storage using IndexedDB with defense-in-depth encryption.
 * Handles access token expiry and automatic refresh flow.
 *
 * Security (Defense in Depth):
 * - Layer 1: iOS automatic encryption (when PWA installed)
 * - Layer 2: Web Crypto API encryption (when browser context)
 * - Layer 3: HTTPS transport (always)
 * - Access tokens: In-memory cache + IndexedDB
 * - Refresh tokens: IndexedDB only (encrypted based on context)
 * - Automatic refresh 5 minutes before expiry
 *
 * Context Detection:
 * - Installed PWA: Uses iOS encryption only
 * - Browser mode: Adds Web Crypto encryption layer
 * - Warns user in browser mode (security recommendation)
 *
 * Philosophy:
 * - Single responsibility: Token lifecycle management
 * - Self-contained with idb library + Web Crypto API
 * - Zero-BS: Real Azure OAuth2 integration
 * - Security First: Never compromise fundamentals
 */

import { openDB, DBSchema, IDBPDatabase } from 'idb';
import PWADetector, { PWAContext } from '../utils/pwa-detector';
import TokenCrypto, { EncryptedToken } from '../utils/token-crypto';

const AZURE_TOKEN_URL = 'https://login.microsoftonline.com/common/oauth2/v2.0/token';
const TOKEN_REFRESH_BUFFER = 5 * 60 * 1000; // 5 minutes in milliseconds

interface TokenDB extends DBSchema {
  'tokens': {
    key: string;
    value: string | EncryptedToken;  // Support both plain and encrypted
  };
}

export class TokenStorage {
  private db: IDBPDatabase<TokenDB> | null = null;
  private memoryCache: Map<string, string> = new Map();
  private pwaContext: PWAContext;
  private securityWarningShown = false;

  constructor() {
    this.pwaContext = PWADetector.detect();
    this.initDB();
    this.showSecurityWarningIfNeeded();
  }

  /**
   * Show security warning if running in browser context
   */
  private showSecurityWarningIfNeeded(): void {
    if (this.securityWarningShown) return;

    const message = PWADetector.getSecurityMessage(this.pwaContext);
    if (message) {
      console.warn('[TokenStorage Security]', message);
      this.securityWarningShown = true;
    }
  }

  /**
   * Initialize IndexedDB
   */
  private async initDB(): Promise<void> {
    if (this.db) return;

    this.db = await openDB<TokenDB>('azlin-tokens', 1, {
      upgrade(db) {
        if (!db.objectStoreNames.contains('tokens')) {
          db.createObjectStore('tokens');
        }
      },
    });
  }

  /**
   * Save tokens to secure storage with context-appropriate encryption
   */
  async saveTokens(
    accessToken: string,
    refreshToken: string,
    expiresOn: number
  ): Promise<void> {
    await this.initDB();

    // Encrypt tokens if running in browser context (not installed PWA)
    if (this.pwaContext.needsEncryption) {
      const encryptedAccess = await TokenCrypto.encrypt(accessToken);
      const encryptedRefresh = await TokenCrypto.encrypt(refreshToken);

      // Save encrypted tokens to IndexedDB
      await this.db!.put('tokens', encryptedAccess, 'azure_access_token');
      await this.db!.put('tokens', encryptedRefresh, 'azure_refresh_token');
    } else {
      // Running as installed PWA - iOS encrypts IndexedDB automatically
      await this.db!.put('tokens', accessToken, 'azure_access_token');
      await this.db!.put('tokens', refreshToken, 'azure_refresh_token');
    }

    // Expiry doesn't need encryption (not sensitive)
    await this.db!.put('tokens', expiresOn.toString(), 'azure_token_expiry');

    // Cache access token in memory (always plaintext in memory)
    this.memoryCache.set('azure_access_token', accessToken);
    this.memoryCache.set('azure_token_expiry', expiresOn.toString());
  }

  /**
   * Get access token, refreshing if expired
   */
  async getAccessToken(): Promise<string> {
    await this.initDB();

    // Try memory cache first
    let token = this.memoryCache.get('azure_access_token');
    let expiry = this.memoryCache.get('azure_token_expiry');

    // Fallback to IndexedDB
    if (!token || !expiry) {
      const storedToken = await this.db!.get('tokens', 'azure_access_token');
      const storedExpiry = await this.db!.get('tokens', 'azure_token_expiry');

      // Decrypt token if it's encrypted
      if (storedToken) {
        token = TokenCrypto.isEncrypted(storedToken)
          ? await TokenCrypto.decrypt(storedToken)
          : storedToken;
      }

      expiry = typeof storedExpiry === 'string' ? storedExpiry : undefined;
    }

    if (!token || !expiry) {
      throw new Error('No access token found. Please authenticate.');
    }

    // Check if token needs refresh (expired or within 5 min buffer)
    const expiryTime = parseInt(expiry);
    const now = Date.now();

    if (now >= expiryTime - TOKEN_REFRESH_BUFFER) {
      return await this.refreshToken();
    }

    return token;
  }

  /**
   * Refresh access token using refresh token
   */
  async refreshToken(): Promise<string> {
    await this.initDB();

    const storedRefreshToken = await this.db!.get('tokens', 'azure_refresh_token');

    if (!storedRefreshToken) {
      throw new Error('No refresh token found. Please re-authenticate.');
    }

    // Decrypt refresh token if it's encrypted
    const refreshToken = TokenCrypto.isEncrypted(storedRefreshToken)
      ? await TokenCrypto.decrypt(storedRefreshToken)
      : storedRefreshToken;

    const clientId = import.meta.env.VITE_AZURE_CLIENT_ID;

    const response = await fetch(AZURE_TOKEN_URL, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
      body: new URLSearchParams({
        client_id: clientId,
        grant_type: 'refresh_token',
        refresh_token: refreshToken,
        scope: 'https://management.azure.com/.default',
      }),
    });

    if (!response.ok) {
      throw new Error(`Token refresh failed: ${response.status} ${response.statusText}`);
    }

    const data = await response.json();

    // Save new tokens
    const expiresOn = Date.now() + (data.expires_in * 1000);
    await this.saveTokens(data.access_token, data.refresh_token, expiresOn);

    return data.access_token;
  }

  /**
   * Clear all tokens (logout)
   */
  async clearTokens(): Promise<void> {
    await this.initDB();

    await this.db!.delete('tokens', 'azure_access_token');
    await this.db!.delete('tokens', 'azure_refresh_token');
    await this.db!.delete('tokens', 'azure_token_expiry');

    this.memoryCache.clear();
  }

  /**
   * Check if user is authenticated
   */
  async isAuthenticated(): Promise<boolean> {
    await this.initDB();

    const token = await this.db!.get('tokens', 'azure_access_token');
    return !!token;
  }

  /**
   * Get PWA security context (for UI to display warnings)
   */
  getSecurityContext(): PWAContext {
    return this.pwaContext;
  }

  /**
   * Get security recommendation message for UI
   */
  getSecurityMessage(): string | null {
    return PWADetector.getSecurityMessage(this.pwaContext);
  }
}

export default TokenStorage;
