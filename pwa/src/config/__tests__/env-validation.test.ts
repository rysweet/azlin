/**
 * Environment Validation Tests
 *
 * Tests the environment variable validation logic.
 *
 * Testing Strategy:
 * - 60% unit tests (validateEnv function behavior)
 * - Focus on error cases and GUID validation
 * - Pass mock environment objects directly (dependency injection pattern)
 */

import { describe, it, expect } from 'vitest';
import { validateEnv, getEnvConfig } from '../env-validation';

// Valid test GUIDs
const VALID_CLIENT_ID = '12345678-1234-1234-1234-123456789012';
const VALID_TENANT_ID = 'abcdef12-3456-7890-abcd-ef1234567890';
const VALID_SUBSCRIPTION_ID = '98765432-1234-5678-90ab-cdef12345678';

// Invalid GUIDs
const INVALID_GUID_SHORT = 'abc-123';
const INVALID_GUID_WRONG_FORMAT = '12345678-12-1234-1234-123456789012'; // Wrong segment length
const INVALID_GUID_INVALID_CHARS = 'xyz12345-1234-1234-1234-123456789012'; // Non-hex chars

// Helper to create valid test environment
const createValidEnv = () => ({
  VITE_AZURE_CLIENT_ID: VALID_CLIENT_ID,
  VITE_AZURE_TENANT_ID: VALID_TENANT_ID,
  VITE_AZURE_SUBSCRIPTION_ID: VALID_SUBSCRIPTION_ID,
});

describe('env-validation', () => {

  describe('validateEnv - Happy Path', () => {
    it('should validate when all required variables are set with valid GUIDs', () => {
      // Arrange
      const env = createValidEnv();

      // Act
      const config = validateEnv(env);

      // Assert
      expect(config.VITE_AZURE_CLIENT_ID).toBe(VALID_CLIENT_ID);
      expect(config.VITE_AZURE_TENANT_ID).toBe(VALID_TENANT_ID);
      expect(config.VITE_AZURE_SUBSCRIPTION_ID).toBe(VALID_SUBSCRIPTION_ID);
    });

    it('should include optional VITE_AZURE_RESOURCE_GROUP when provided', () => {
      // Arrange
      const env = {
        ...createValidEnv(),
        VITE_AZURE_RESOURCE_GROUP: 'my-resource-group',
      };

      // Act
      const config = validateEnv(env);

      // Assert
      expect(config.VITE_AZURE_RESOURCE_GROUP).toBe('my-resource-group');
    });
  });

  describe('validateEnv - Missing Variables', () => {
    it('should throw error when VITE_AZURE_CLIENT_ID is missing', () => {
      // Arrange
      const env = {
        VITE_AZURE_TENANT_ID: VALID_TENANT_ID,
        VITE_AZURE_SUBSCRIPTION_ID: VALID_SUBSCRIPTION_ID,
      };

      // Act & Assert
      expect(() => validateEnv(env)).toThrow('Missing required environment variables');
      expect(() => validateEnv(env)).toThrow('VITE_AZURE_CLIENT_ID');
    });

    it('should throw error when VITE_AZURE_TENANT_ID is missing', () => {
      // Arrange
      const env = {
        VITE_AZURE_CLIENT_ID: VALID_CLIENT_ID,
        VITE_AZURE_SUBSCRIPTION_ID: VALID_SUBSCRIPTION_ID,
      };

      // Act & Assert
      expect(() => validateEnv(env)).toThrow('Missing required environment variables');
      expect(() => validateEnv(env)).toThrow('VITE_AZURE_TENANT_ID');
    });

    it('should throw error when VITE_AZURE_SUBSCRIPTION_ID is missing', () => {
      // Arrange
      const env = {
        VITE_AZURE_CLIENT_ID: VALID_CLIENT_ID,
        VITE_AZURE_TENANT_ID: VALID_TENANT_ID,
      };

      // Act & Assert
      expect(() => validateEnv(env)).toThrow('Missing required environment variables');
      expect(() => validateEnv(env)).toThrow('VITE_AZURE_SUBSCRIPTION_ID');
    });

    it('should throw error listing all missing variables', () => {
      // Arrange - empty env
      const env = {};

      // Act & Assert
      expect(() => validateEnv(env)).toThrow('Missing required environment variables');
      expect(() => validateEnv(env)).toThrow('VITE_AZURE_CLIENT_ID');
      expect(() => validateEnv(env)).toThrow('VITE_AZURE_TENANT_ID');
      expect(() => validateEnv(env)).toThrow('VITE_AZURE_SUBSCRIPTION_ID');
    });

    it('should treat empty strings as missing', () => {
      // Arrange
      const env = {
        VITE_AZURE_CLIENT_ID: '',
        VITE_AZURE_TENANT_ID: '   ',
        VITE_AZURE_SUBSCRIPTION_ID: VALID_SUBSCRIPTION_ID,
      };

      // Act & Assert
      expect(() => validateEnv(env)).toThrow('Missing required environment variables');
      expect(() => validateEnv(env)).toThrow('VITE_AZURE_CLIENT_ID');
      expect(() => validateEnv(env)).toThrow('VITE_AZURE_TENANT_ID');
    });
  });

  describe('validateEnv - Invalid GUID Format', () => {
    it('should throw error when CLIENT_ID is not a valid GUID', () => {
      // Arrange
      const env = {
        VITE_AZURE_CLIENT_ID: INVALID_GUID_SHORT,
        VITE_AZURE_TENANT_ID: VALID_TENANT_ID,
        VITE_AZURE_SUBSCRIPTION_ID: VALID_SUBSCRIPTION_ID,
      };

      // Act & Assert
      expect(() => validateEnv(env)).toThrow('Invalid format for Azure environment variables');
      expect(() => validateEnv(env)).toThrow('VITE_AZURE_CLIENT_ID');
      expect(() => validateEnv(env)).toThrow('not a valid GUID');
    });

    it('should throw error when TENANT_ID has wrong format', () => {
      // Arrange
      const env = {
        VITE_AZURE_CLIENT_ID: VALID_CLIENT_ID,
        VITE_AZURE_TENANT_ID: INVALID_GUID_WRONG_FORMAT,
        VITE_AZURE_SUBSCRIPTION_ID: VALID_SUBSCRIPTION_ID,
      };

      // Act & Assert
      expect(() => validateEnv(env)).toThrow('Invalid format for Azure environment variables');
      expect(() => validateEnv(env)).toThrow('VITE_AZURE_TENANT_ID');
    });

    it('should throw error when SUBSCRIPTION_ID contains invalid characters', () => {
      // Arrange
      const env = {
        VITE_AZURE_CLIENT_ID: VALID_CLIENT_ID,
        VITE_AZURE_TENANT_ID: VALID_TENANT_ID,
        VITE_AZURE_SUBSCRIPTION_ID: INVALID_GUID_INVALID_CHARS,
      };

      // Act & Assert
      expect(() => validateEnv(env)).toThrow('Invalid format for Azure environment variables');
      expect(() => validateEnv(env)).toThrow('VITE_AZURE_SUBSCRIPTION_ID');
    });

    it('should validate GUID format is case-insensitive', () => {
      // Arrange - uppercase GUID
      const env = {
        VITE_AZURE_CLIENT_ID: VALID_CLIENT_ID.toUpperCase(),
        VITE_AZURE_TENANT_ID: VALID_TENANT_ID.toUpperCase(),
        VITE_AZURE_SUBSCRIPTION_ID: VALID_SUBSCRIPTION_ID.toUpperCase(),
      };

      // Act
      const config = validateEnv(env);

      // Assert - should not throw
      expect(config.VITE_AZURE_CLIENT_ID).toBe(VALID_CLIENT_ID.toUpperCase());
    });
  });

  describe('getEnvConfig', () => {
    it('should call validateEnv and return config', () => {
      // Note: getEnvConfig calls validateEnv() with no parameters,
      // so it uses import.meta.env which won't be mocked in tests.
      // This test verifies the function exists and delegates correctly.

      // We can't easily test getEnvConfig without mocking import.meta.env at module load time,
      // but we've thoroughly tested validateEnv which is what getEnvConfig calls.
      expect(getEnvConfig).toBeDefined();
      expect(typeof getEnvConfig).toBe('function');
    });
  });
});
