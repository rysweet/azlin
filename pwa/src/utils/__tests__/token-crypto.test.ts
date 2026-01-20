/**
 * Unit Tests for Token Encryption
 *
 * Tests AES-GCM encryption for tokens in browser context.
 * Critical for security when PWA is not installed.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import TokenCrypto, { EncryptedToken } from '../token-crypto';

describe('TokenCrypto', () => {
  // Mock Web Crypto API if not available
  beforeEach(() => {
    if (!globalThis.crypto) {
      Object.defineProperty(globalThis, 'crypto', {
        value: {
          subtle: {
            digest: vi.fn(),
            importKey: vi.fn(),
            encrypt: vi.fn(),
            decrypt: vi.fn(),
          },
          getRandomValues: vi.fn((arr) => {
            for (let i = 0; i < arr.length; i++) {
              arr[i] = Math.floor(Math.random() * 256);
            }
            return arr;
          }),
        },
        writable: true,
      });
    }
  });

  describe('encrypt', () => {
    it('should encrypt a token successfully', async () => {
      const token = 'test_access_token_12345';

      const encrypted = await TokenCrypto.encrypt(token);

      expect(encrypted).toBeDefined();
      expect(encrypted.ciphertext).toBeTruthy();
      expect(encrypted.iv).toBeTruthy();
      expect(encrypted.version).toBe(1);
    });

    it('should produce different ciphertext each time (unique IV)', async () => {
      const token = 'test_access_token_12345';

      const encrypted1 = await TokenCrypto.encrypt(token);
      const encrypted2 = await TokenCrypto.encrypt(token);

      // Different IVs
      expect(encrypted1.iv).not.toBe(encrypted2.iv);
      // Different ciphertexts (due to different IVs)
      expect(encrypted1.ciphertext).not.toBe(encrypted2.ciphertext);
    });

    it('should reject empty tokens', async () => {
      await expect(TokenCrypto.encrypt('')).rejects.toThrow('Cannot encrypt empty token');
    });

    it('should reject whitespace-only tokens', async () => {
      await expect(TokenCrypto.encrypt('   ')).rejects.toThrow('Cannot encrypt empty token');
    });

    it('should handle encryption errors gracefully', async () => {
      const originalEncrypt = crypto.subtle.encrypt;
      crypto.subtle.encrypt = vi.fn().mockRejectedValue(new Error('Encryption failed'));

      await expect(TokenCrypto.encrypt('token')).rejects.toThrow('Token encryption failed');

      crypto.subtle.encrypt = originalEncrypt;
    });
  });

  describe('decrypt', () => {
    it('should decrypt an encrypted token', async () => {
      const originalToken = 'test_access_token_12345';

      const encrypted = await TokenCrypto.encrypt(originalToken);
      const decrypted = await TokenCrypto.decrypt(encrypted);

      expect(decrypted).toBe(originalToken);
    });

    it('should handle long tokens', async () => {
      const longToken = 'a'.repeat(1000);

      const encrypted = await TokenCrypto.encrypt(longToken);
      const decrypted = await TokenCrypto.decrypt(encrypted);

      expect(decrypted).toBe(longToken);
    });

    it('should handle special characters', async () => {
      const specialToken = 'token!@#$%^&*()_+-=[]{}|;:,.<>?';

      const encrypted = await TokenCrypto.encrypt(specialToken);
      const decrypted = await TokenCrypto.decrypt(encrypted);

      expect(decrypted).toBe(specialToken);
    });

    it('should reject invalid encrypted token format', async () => {
      const invalid = { ciphertext: 'test' } as EncryptedToken;

      await expect(TokenCrypto.decrypt(invalid)).rejects.toThrow('Invalid encrypted token format');
    });

    it('should reject unsupported encryption version', async () => {
      const unsupported: EncryptedToken = {
        ciphertext: 'dGVzdA==',
        iv: 'dGVzdA==',
        version: 999,
      };

      await expect(TokenCrypto.decrypt(unsupported)).rejects.toThrow('Unsupported encryption version');
    });

    it('should handle decryption errors gracefully', async () => {
      const encrypted: EncryptedToken = {
        ciphertext: 'invalid_base64',
        iv: 'invalid_base64',
        version: 1,
      };

      await expect(TokenCrypto.decrypt(encrypted)).rejects.toThrow('Token decryption failed');
    });
  });

  describe('isEncrypted', () => {
    it('should detect encrypted token', () => {
      const encrypted: EncryptedToken = {
        ciphertext: 'dGVzdA==',
        iv: 'dGVzdA==',
        version: 1,
      };

      expect(TokenCrypto.isEncrypted(encrypted)).toBe(true);
    });

    it('should reject plain string', () => {
      const plain = 'test_token';

      expect(TokenCrypto.isEncrypted(plain)).toBe(false);
    });

    it('should reject null', () => {
      expect(TokenCrypto.isEncrypted(null)).toBe(false);
    });

    it('should reject undefined', () => {
      expect(TokenCrypto.isEncrypted(undefined)).toBe(false);
    });

    it('should reject partial encrypted token', () => {
      const partial = { ciphertext: 'test' };

      expect(TokenCrypto.isEncrypted(partial)).toBe(false);
    });
  });

  describe('encryption consistency', () => {
    it('should use same key for same device fingerprint', async () => {
      const token = 'test_token';

      // Encrypt twice
      const encrypted1 = await TokenCrypto.encrypt(token);
      const encrypted2 = await TokenCrypto.encrypt(token);

      // Should decrypt successfully (same key)
      const decrypted1 = await TokenCrypto.decrypt(encrypted1);
      const decrypted2 = await TokenCrypto.decrypt(encrypted2);

      expect(decrypted1).toBe(token);
      expect(decrypted2).toBe(token);
    });

    it('should maintain consistency across multiple encrypt/decrypt cycles', async () => {
      const token = 'test_token_cycle';

      for (let i = 0; i < 10; i++) {
        const encrypted = await TokenCrypto.encrypt(token);
        const decrypted = await TokenCrypto.decrypt(encrypted);

        expect(decrypted).toBe(token);
      }
    });
  });

  describe('security properties', () => {
    it('should use unique IV for each encryption', async () => {
      const token = 'test_token';
      const ivs = new Set<string>();

      for (let i = 0; i < 100; i++) {
        const encrypted = await TokenCrypto.encrypt(token);
        ivs.add(encrypted.iv);
      }

      // All IVs should be unique
      expect(ivs.size).toBe(100);
    });

    it('should produce non-trivial ciphertext', async () => {
      const token = 'short';

      const encrypted = await TokenCrypto.encrypt(token);

      // Ciphertext should be longer than plaintext (includes auth tag)
      expect(encrypted.ciphertext.length).toBeGreaterThan(token.length);
    });
  });
});
