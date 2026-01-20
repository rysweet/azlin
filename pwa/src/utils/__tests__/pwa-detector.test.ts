/**
 * Unit Tests for PWA Detector
 *
 * Tests PWA installation detection and security context.
 * Critical for security decisions (encryption layer selection).
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import PWADetector, { PWAContext } from '../pwa-detector';

describe('PWADetector', () => {
  let originalUserAgent: string;

  beforeEach(() => {
    vi.clearAllMocks();
    originalUserAgent = navigator.userAgent;

    // Clear navigator.standalone (iOS Safari property)
    delete (navigator as any).standalone;

    // Reset matchMedia to default (browser mode)
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
  });

  afterEach(() => {
    // Restore original userAgent
    Object.defineProperty(navigator, 'userAgent', {
      value: originalUserAgent,
      configurable: true,
    });

    // Clear navigator.standalone
    delete (navigator as any).standalone;
  });

  describe('detectDisplayMode', () => {
    it('should detect standalone mode (installed PWA)', () => {
      // Mock matchMedia to return standalone
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

      const context = PWADetector.detect();

      expect(context.displayMode).toBe('standalone');
      expect(context.isInstalled).toBe(true);
    });

    it('should detect browser mode (not installed)', () => {
      // Mock matchMedia to return browser
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

      const context = PWADetector.detect();

      expect(context.displayMode).toBe('browser');
      expect(context.isInstalled).toBe(false);
    });

    it('should detect fullscreen mode', () => {
      window.matchMedia = vi.fn((query) => ({
        matches: query === '(display-mode: fullscreen)',
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })) as any;

      const context = PWADetector.detect();

      expect(context.displayMode).toBe('fullscreen');
      expect(context.isInstalled).toBe(true);
    });

    it('should fallback to navigator.standalone for iOS', () => {
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

      (navigator as any).standalone = true;

      const context = PWADetector.detect();

      expect(context.displayMode).toBe('standalone');
      expect(context.isInstalled).toBe(true);
    });
  });

  describe('detectPlatform', () => {
    it('should detect iOS platform', () => {
      Object.defineProperty(navigator, 'userAgent', {
        value: 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X)',
        configurable: true,
      });

      const context = PWADetector.detect();

      expect(context.platform).toBe('ios');
    });

    it('should detect iPad as iOS', () => {
      Object.defineProperty(navigator, 'userAgent', {
        value: 'Mozilla/5.0 (iPad; CPU OS 15_0 like Mac OS X)',
        configurable: true,
      });

      const context = PWADetector.detect();

      expect(context.platform).toBe('ios');
    });

    it('should detect Android platform', () => {
      Object.defineProperty(navigator, 'userAgent', {
        value: 'Mozilla/5.0 (Linux; Android 11)',
        configurable: true,
      });

      const context = PWADetector.detect();

      expect(context.platform).toBe('android');
    });

    it('should detect desktop platform', () => {
      Object.defineProperty(navigator, 'userAgent', {
        value: 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        configurable: true,
      });

      const context = PWADetector.detect();

      expect(context.platform).toBe('desktop');
    });
  });

  describe('needsEncryption', () => {
    it('should require encryption for iOS in browser mode', () => {
      Object.defineProperty(navigator, 'userAgent', {
        value: 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X)',
        configurable: true,
      });

      window.matchMedia = vi.fn((query) => ({
        matches: false,  // Browser mode
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })) as any;

      const context = PWADetector.detect();

      expect(context.needsEncryption).toBe(true);
      expect(context.platform).toBe('ios');
      expect(context.isInstalled).toBe(false);
    });

    it('should NOT require encryption for iOS in installed PWA mode', () => {
      Object.defineProperty(navigator, 'userAgent', {
        value: 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_0 like Mac OS X)',
        configurable: true,
      });

      window.matchMedia = vi.fn((query) => ({
        matches: query === '(display-mode: standalone)',  // Installed
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })) as any;

      const context = PWADetector.detect();

      expect(context.needsEncryption).toBe(false);
      expect(context.platform).toBe('ios');
      expect(context.isInstalled).toBe(true);
    });

    it('should NOT require encryption for Android in browser mode', () => {
      Object.defineProperty(navigator, 'userAgent', {
        value: 'Mozilla/5.0 (Linux; Android 11)',
        configurable: true,
      });

      window.matchMedia = vi.fn((query) => ({
        matches: false,  // Browser mode
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })) as any;

      const context = PWADetector.detect();

      expect(context.needsEncryption).toBe(false);
      expect(context.platform).toBe('android');
      expect(context.isInstalled).toBe(false);
    });
  });

  describe('getSecurityMessage', () => {
    it('should return warning for iOS browser mode', () => {
      const context: PWAContext = {
        isInstalled: false,
        displayMode: 'browser',
        platform: 'ios',
        needsEncryption: true,
      };

      const message = PWADetector.getSecurityMessage(context);

      expect(message).toBeTruthy();
      expect(message).toContain('Warning');
      expect(message).toContain('browser mode');
    });

    it('should return null for installed PWA', () => {
      const context: PWAContext = {
        isInstalled: true,
        displayMode: 'standalone',
        platform: 'ios',
        needsEncryption: false,
      };

      const message = PWADetector.getSecurityMessage(context);

      expect(message).toBeNull();
    });

    it('should return null for non-iOS platforms', () => {
      const context: PWAContext = {
        isInstalled: false,
        displayMode: 'browser',
        platform: 'android',
        needsEncryption: false,
      };

      const message = PWADetector.getSecurityMessage(context);

      expect(message).toBeNull();
    });
  });

  describe('canInstall', () => {
    it('should return true if beforeinstallprompt event was captured', () => {
      (window as any).deferredPrompt = {};

      const canInstall = PWADetector.canInstall();

      expect(canInstall).toBe(true);
    });

    it('should return false if no beforeinstallprompt event', () => {
      delete (window as any).deferredPrompt;

      const canInstall = PWADetector.canInstall();

      expect(canInstall).toBe(false);
    });
  });
});
