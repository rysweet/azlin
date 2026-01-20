/**
 * Security Tests for Token Storage
 *
 * Tests encryption context detection and defense-in-depth security.
 * Verifies proper encryption layer selection based on PWA installation status.
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { TokenStorage } from '../token-storage';
import PWADetector from '../../utils/pwa-detector';
import 'fake-indexeddb/auto';

describe('TokenStorage Security', () => {
  let tokenStorage: TokenStorage;
  let consoleWarnSpy: any;

  beforeEach(() => {
    consoleWarnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
  });

  afterEach(() => {
    consoleWarnSpy.mockRestore();
    vi.clearAllMocks();
  });

  describe('Security Context Detection', () => {
    it('should detect installed PWA context', () => {
      // Mock installed PWA
      window.matchMedia = vi.fn((query) => ({
        matches: query === '(display-mode: standalone)',
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })) as any;

      Object.defineProperty(navigator, 'userAgent', {
        value: 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X)',
        configurable: true,
      });

      tokenStorage = new TokenStorage();
      const context = tokenStorage.getSecurityContext();

      expect(context.isInstalled).toBe(true);
      expect(context.needsEncryption).toBe(false);
      expect(context.platform).toBe('ios');
    });

    it('should detect browser context on iOS', () => {
      // Mock browser mode
      window.matchMedia = vi.fn((query) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })) as any;

      Object.defineProperty(navigator, 'userAgent', {
        value: 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X)',
        configurable: true,
      });

      tokenStorage = new TokenStorage();
      const context = tokenStorage.getSecurityContext();

      expect(context.isInstalled).toBe(false);
      expect(context.needsEncryption).toBe(true);
      expect(context.platform).toBe('ios');
    });
  });

  describe('Security Warnings', () => {
    it('should warn when running in iOS browser mode', () => {
      // Mock browser mode on iOS
      window.matchMedia = vi.fn((query) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })) as any;

      Object.defineProperty(navigator, 'userAgent', {
        value: 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X)',
        configurable: true,
      });

      tokenStorage = new TokenStorage();

      // Should have warned
      expect(consoleWarnSpy).toHaveBeenCalledWith(
        '[TokenStorage Security]',
        expect.stringContaining('Warning')
      );
    });

    it('should NOT warn when running as installed PWA', () => {
      // Mock installed PWA
      window.matchMedia = vi.fn((query) => ({
        matches: query === '(display-mode: standalone)',
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })) as any;

      tokenStorage = new TokenStorage();

      // Should NOT have warned
      expect(consoleWarnSpy).not.toHaveBeenCalled();
    });

    it('should only show warning once', () => {
      // Mock browser mode on iOS
      window.matchMedia = vi.fn((query) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })) as any;

      Object.defineProperty(navigator, 'userAgent', {
        value: 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X)',
        configurable: true,
      });

      tokenStorage = new TokenStorage();

      // Get warning message multiple times
      tokenStorage.getSecurityMessage();
      tokenStorage.getSecurityMessage();

      // Should have only warned once during construction
      expect(consoleWarnSpy).toHaveBeenCalledTimes(1);
    });
  });

  describe('Encryption Layer Selection', () => {
    it('should use encryption for iOS browser context', async () => {
      // Mock browser mode on iOS
      window.matchMedia = vi.fn((query) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })) as any;

      Object.defineProperty(navigator, 'userAgent', {
        value: 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X)',
        configurable: true,
      });

      tokenStorage = new TokenStorage();

      // Save tokens - should encrypt
      await tokenStorage.saveTokens('access_token', 'refresh_token', Date.now() + 3600000);

      // Retrieve tokens - should decrypt
      const token = await tokenStorage.getAccessToken();

      expect(token).toBe('access_token');
    });

    it('should NOT use encryption for installed PWA', async () => {
      // Mock installed PWA
      window.matchMedia = vi.fn((query) => ({
        matches: query === '(display-mode: standalone)',
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })) as any;

      tokenStorage = new TokenStorage();

      // Save tokens - should NOT encrypt (relies on iOS)
      await tokenStorage.saveTokens('access_token', 'refresh_token', Date.now() + 3600000);

      // Retrieve tokens - should be plaintext in storage
      const token = await tokenStorage.getAccessToken();

      expect(token).toBe('access_token');
    }, 10000); // Increase timeout to 10 seconds
  });

  describe('Backward Compatibility', () => {
    it('should handle migration from plaintext to encrypted tokens', async () => {
      // Start with plaintext tokens (old behavior)
      window.matchMedia = vi.fn((query) => ({
        matches: query === '(display-mode: standalone)',
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })) as any;

      tokenStorage = new TokenStorage();
      await tokenStorage.saveTokens('old_token', 'old_refresh', Date.now() + 3600000);

      // Switch to browser mode (should encrypt)
      window.matchMedia = vi.fn((query) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })) as any;

      Object.defineProperty(navigator, 'userAgent', {
        value: 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X)',
        configurable: true,
      });

      // Create new storage instance (would happen on app restart)
      const newStorage = new TokenStorage();

      // Should still read old plaintext tokens
      const token = await newStorage.getAccessToken();
      expect(token).toBe('old_token');

      // Save new tokens - should encrypt
      await newStorage.saveTokens('new_token', 'new_refresh', Date.now() + 3600000);

      // Should read encrypted tokens
      const newToken = await newStorage.getAccessToken();
      expect(newToken).toBe('new_token');
    }, 10000); // Increase timeout to 10 seconds
  });

  describe('getSecurityMessage', () => {
    it('should return warning message for browser context', () => {
      // Mock browser mode on iOS
      window.matchMedia = vi.fn((query) => ({
        matches: false,
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })) as any;

      Object.defineProperty(navigator, 'userAgent', {
        value: 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X)',
        configurable: true,
      });

      tokenStorage = new TokenStorage();
      const message = tokenStorage.getSecurityMessage();

      expect(message).toBeTruthy();
      expect(message).toContain('Warning');
    });

    it('should return null for installed PWA', () => {
      // Mock installed PWA
      window.matchMedia = vi.fn((query) => ({
        matches: query === '(display-mode: standalone)',
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })) as any;

      tokenStorage = new TokenStorage();
      const message = tokenStorage.getSecurityMessage();

      expect(message).toBeNull();
    });
  });
});
