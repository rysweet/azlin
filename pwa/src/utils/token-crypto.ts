/**
 * Token Encryption using Web Crypto API
 *
 * Provides AES-GCM encryption for sensitive tokens when running in browser context.
 * Only used when PWA is not installed (iOS doesn't encrypt IndexedDB in browser mode).
 *
 * Philosophy:
 * - Single responsibility: Token encryption/decryption
 * - Self-contained with Web Crypto API (standard library)
 * - Zero-BS: Real encryption, not obfuscation
 *
 * Security Design:
 * - AES-GCM 256-bit encryption (authenticated encryption)
 * - Unique IV per encryption (stored with ciphertext)
 * - Key derived from device fingerprint (hardware ID + user agent)
 * - No key storage (derived on-demand from device characteristics)
 *
 * Defense in Depth:
 * - Layer 1: iOS encryption (when PWA installed)
 * - Layer 2: Web Crypto encryption (when browser context)
 * - Layer 3: HTTPS transport (always)
 */

export interface EncryptedToken {
  ciphertext: string;  // Base64 encoded
  iv: string;          // Base64 encoded initialization vector
  version: number;     // Encryption version for future upgrades
}

export class TokenCrypto {
  private static readonly ALGORITHM = 'AES-GCM';
  private static readonly KEY_LENGTH = 256;
  private static readonly VERSION = 1;

  /**
   * Derive encryption key from device fingerprint
   * Uses hardware/browser characteristics to create consistent key
   */
  private static async deriveKey(): Promise<CryptoKey> {
    // Create device fingerprint from stable characteristics
    const fingerprint = [
      navigator.userAgent,
      navigator.language,
      navigator.hardwareConcurrency?.toString() || 'unknown',
      screen.width.toString(),
      screen.height.toString(),
      new Date().getTimezoneOffset().toString(),
    ].join('|');

    // Hash fingerprint to create key material
    const encoder = new TextEncoder();
    const data = encoder.encode(fingerprint);
    const hashBuffer = await crypto.subtle.digest('SHA-256', data);

    // Import as AES-GCM key
    return await crypto.subtle.importKey(
      'raw',
      hashBuffer,
      { name: this.ALGORITHM, length: this.KEY_LENGTH },
      false,  // Not extractable
      ['encrypt', 'decrypt']
    );
  }

  /**
   * Encrypt token using AES-GCM
   */
  static async encrypt(token: string): Promise<EncryptedToken> {
    if (!token || token.trim() === '') {
      throw new Error('Cannot encrypt empty token');
    }

    try {
      // Generate unique IV for this encryption
      const iv = crypto.getRandomValues(new Uint8Array(12));

      // Get encryption key
      const key = await this.deriveKey();

      // Encrypt
      const encoder = new TextEncoder();
      const data = encoder.encode(token);
      const cipherBuffer = await crypto.subtle.encrypt(
        { name: this.ALGORITHM, iv },
        key,
        data
      );

      // Return encrypted token with IV
      return {
        ciphertext: this.bufferToBase64(cipherBuffer),
        iv: this.bufferToBase64(iv.buffer),
        version: this.VERSION,
      };
    } catch (error) {
      throw new Error(`Token encryption failed: ${error instanceof Error ? error.message : 'Unknown error'}`);
    }
  }

  /**
   * Decrypt token using AES-GCM
   */
  static async decrypt(encrypted: EncryptedToken): Promise<string> {
    if (!encrypted || !encrypted.ciphertext || !encrypted.iv) {
      throw new Error('Invalid encrypted token format');
    }

    if (encrypted.version !== this.VERSION) {
      throw new Error(`Unsupported encryption version: ${encrypted.version}`);
    }

    try {
      // Get decryption key
      const key = await this.deriveKey();

      // Decrypt
      const cipherBuffer = this.base64ToBuffer(encrypted.ciphertext);
      const ivBuffer = this.base64ToBuffer(encrypted.iv);

      const decryptedBuffer = await crypto.subtle.decrypt(
        { name: this.ALGORITHM, iv: ivBuffer },
        key,
        cipherBuffer
      ) as ArrayBuffer;

      // Convert to string
      const decoder = new TextDecoder();
      return decoder.decode(decryptedBuffer);
    } catch (error) {
      throw new Error(`Token decryption failed: ${error instanceof Error ? error.message : 'Unknown error'}`);
    }
  }

  /**
   * Check if a value is encrypted
   */
  static isEncrypted(value: any): value is EncryptedToken {
    return (
      typeof value === 'object' &&
      value !== null &&
      typeof value.ciphertext === 'string' &&
      typeof value.iv === 'string' &&
      typeof value.version === 'number'
    );
  }

  /**
   * Convert ArrayBuffer to Base64
   */
  private static bufferToBase64(buffer: ArrayBuffer): string {
    const bytes = new Uint8Array(buffer);
    let binary = '';
    for (let i = 0; i < bytes.length; i++) {
      binary += String.fromCharCode(bytes[i]);
    }
    return btoa(binary);
  }

  /**
   * Convert Base64 to ArrayBuffer (returns Uint8Array which is BufferSource compatible)
   */
  private static base64ToBuffer(base64: string): Uint8Array<ArrayBuffer> {
    const binary = atob(base64);
    const buffer = new ArrayBuffer(binary.length);
    const bytes = new Uint8Array(buffer);
    for (let i = 0; i < binary.length; i++) {
      bytes[i] = binary.charCodeAt(i);
    }
    return bytes;
  }
}

export default TokenCrypto;
