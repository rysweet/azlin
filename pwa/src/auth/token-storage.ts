/**
 * Token Storage for Azlin Mobile PWA
 *
 * Secure token storage using IndexedDB with automatic iOS encryption.
 * Handles access token expiry and automatic refresh flow.
 *
 * Security:
 * - Access tokens: In-memory cache + IndexedDB
 * - Refresh tokens: IndexedDB only (encrypted by iOS automatically)
 * - Automatic refresh 5 minutes before expiry
 *
 * Philosophy:
 * - Single responsibility: Token lifecycle management
 * - Self-contained with idb library
 * - Zero-BS: Real Azure OAuth2 integration
 */

import { openDB, DBSchema, IDBPDatabase } from 'idb';

const AZURE_TOKEN_URL = 'https://login.microsoftonline.com/common/oauth2/v2.0/token';
const TOKEN_REFRESH_BUFFER = 5 * 60 * 1000; // 5 minutes in milliseconds

interface TokenDB extends DBSchema {
  'tokens': {
    key: string;
    value: string;
  };
}

export class TokenStorage {
  private db: IDBPDatabase<TokenDB> | null = null;
  private memoryCache: Map<string, string> = new Map();

  constructor() {
    this.initDB();
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
   * Save tokens to secure storage
   */
  async saveTokens(
    accessToken: string,
    refreshToken: string,
    expiresOn: number
  ): Promise<void> {
    await this.initDB();

    // Save to IndexedDB
    await this.db!.put('tokens', accessToken, 'azure_access_token');
    await this.db!.put('tokens', refreshToken, 'azure_refresh_token');
    await this.db!.put('tokens', expiresOn.toString(), 'azure_token_expiry');

    // Cache access token in memory
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
      token = await this.db!.get('tokens', 'azure_access_token');
      expiry = await this.db!.get('tokens', 'azure_token_expiry');
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

    const refreshToken = await this.db!.get('tokens', 'azure_refresh_token');

    if (!refreshToken) {
      throw new Error('No refresh token found. Please re-authenticate.');
    }

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
}

export default TokenStorage;
