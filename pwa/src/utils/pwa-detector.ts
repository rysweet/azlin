/**
 * PWA Installation Detection Utility
 *
 * Detects if the app is running as an installed PWA or in browser context.
 * Critical for security decisions (iOS only encrypts IndexedDB for installed PWAs).
 *
 * Philosophy:
 * - Single responsibility: PWA context detection
 * - Self-contained with no external dependencies
 * - Zero-BS: Real detection, no assumptions
 *
 * Security Note:
 * - Installed PWA: IndexedDB automatically encrypted by iOS
 * - Browser context: IndexedDB NOT encrypted, requires manual encryption
 */

export interface PWAContext {
  isInstalled: boolean;
  displayMode: 'standalone' | 'browser' | 'minimal-ui' | 'fullscreen';
  platform: 'ios' | 'android' | 'desktop' | 'unknown';
  needsEncryption: boolean;  // true if running in browser (not PWA)
}

export class PWADetector {
  /**
   * Detect PWA installation status and context
   */
  static detect(): PWAContext {
    const displayMode = this.detectDisplayMode();
    const platform = this.detectPlatform();
    const isInstalled = displayMode === 'standalone' || displayMode === 'fullscreen';

    // Need manual encryption if:
    // 1. Running in browser (not installed as PWA)
    // 2. On iOS (where this matters most)
    const needsEncryption = !isInstalled && platform === 'ios';

    return {
      isInstalled,
      displayMode,
      platform,
      needsEncryption,
    };
  }

  /**
   * Detect display mode (standalone = installed PWA)
   */
  private static detectDisplayMode(): PWAContext['displayMode'] {
    // Check display-mode media query (most reliable)
    if (window.matchMedia('(display-mode: standalone)').matches) {
      return 'standalone';
    }
    if (window.matchMedia('(display-mode: fullscreen)').matches) {
      return 'fullscreen';
    }
    if (window.matchMedia('(display-mode: minimal-ui)').matches) {
      return 'minimal-ui';
    }

    // Fallback: Check navigator.standalone (iOS Safari)
    if ((navigator as any).standalone === true) {
      return 'standalone';
    }

    return 'browser';
  }

  /**
   * Detect platform
   */
  private static detectPlatform(): PWAContext['platform'] {
    const userAgent = navigator.userAgent.toLowerCase();

    if (/iphone|ipad|ipod/.test(userAgent)) {
      return 'ios';
    }
    if (/android/.test(userAgent)) {
      return 'android';
    }
    if (/windows|mac|linux/.test(userAgent)) {
      return 'desktop';
    }

    return 'unknown';
  }

  /**
   * Check if PWA is installable but not installed
   */
  static canInstall(): boolean {
    // Check if beforeinstallprompt was captured
    return (window as any).deferredPrompt !== undefined;
  }

  /**
   * Get security recommendation message
   */
  static getSecurityMessage(context: PWAContext): string | null {
    if (context.needsEncryption) {
      return 'Warning: Running in browser mode. For maximum security, install this app to your home screen.';
    }
    return null;
  }
}

export default PWADetector;
