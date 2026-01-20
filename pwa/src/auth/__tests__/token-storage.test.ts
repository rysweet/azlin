/**
 * Unit Tests for Token Storage (60% of testing pyramid)
 *
 * Tests secure token storage using IndexedDB.
 */

import 'fake-indexeddb/auto';
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { TokenStorage } from '../token-storage';

describe('TokenStorage', () => {
  let tokenStorage: TokenStorage;

  beforeEach(() => {
    tokenStorage = new TokenStorage();
  });

  afterEach(async () => {
    vi.clearAllMocks();
    // Clean up IndexedDB between tests
    await tokenStorage.clearTokens();
  });

  describe('saveTokens', () => {
    it('should save tokens successfully', async () => {
      const accessToken = 'mock_access_token';
      const refreshToken = 'mock_refresh_token';
      const expiresOn = Date.now() + 3600000;

      await expect(
        tokenStorage.saveTokens(accessToken, refreshToken, expiresOn)
      ).resolves.not.toThrow();
    });

    it('should make tokens retrievable', async () => {
      const accessToken = 'mock_access_token';
      const refreshToken = 'mock_refresh_token';
      const expiresOn = Date.now() + 3600000;

      await tokenStorage.saveTokens(accessToken, refreshToken, expiresOn);

      const retrieved = await tokenStorage.getAccessToken();
      expect(retrieved).toBe(accessToken);
    });
  });

  describe('getAccessToken', () => {
    it('should return valid access token', async () => {
      const accessToken = 'mock_access_token';
      const refreshToken = 'mock_refresh_token';
      const futureExpiry = Date.now() + 3600000;

      await tokenStorage.saveTokens(accessToken, refreshToken, futureExpiry);
      const token = await tokenStorage.getAccessToken();

      expect(token).toBe('mock_access_token');
    });

    it('should handle missing tokens', async () => {
      await expect(tokenStorage.getAccessToken()).rejects.toThrow();
    });
  });

  describe('refreshToken', () => {
    beforeEach(() => {
      global.fetch = vi.fn();
    });

    it('should handle refresh failure when no refresh token exists', async () => {
      // No tokens saved
      await expect(tokenStorage.refreshToken()).rejects.toThrow();
    });

    it('should handle network errors', async () => {
      // Save tokens first
      await tokenStorage.saveTokens('old_token', 'mock_refresh', Date.now() + 3600000);

      (global.fetch as any).mockRejectedValue(new Error('Network error'));

      await expect(tokenStorage.refreshToken()).rejects.toThrow();
    });
  });

  describe('clearTokens', () => {
    it('should clear all tokens', async () => {
      // Save tokens first
      await tokenStorage.saveTokens('token', 'refresh', Date.now() + 3600000);

      // Verify saved
      expect(await tokenStorage.isAuthenticated()).toBe(true);

      // Clear
      await tokenStorage.clearTokens();

      // Verify cleared
      expect(await tokenStorage.isAuthenticated()).toBe(false);
    });
  });

  describe('isAuthenticated', () => {
    it('should return true for valid token', async () => {
      const futureExpiry = Date.now() + 3600000;
      await tokenStorage.saveTokens('token', 'refresh', futureExpiry);

      const isValid = await tokenStorage.isAuthenticated();
      expect(isValid).toBe(true);
    });

    it('should return false when no token exists', async () => {
      const isValid = await tokenStorage.isAuthenticated();
      expect(isValid).toBe(false);
    });
  });
});
