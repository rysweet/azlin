/**
 * Environment Variable Validation for Azlin Mobile PWA
 *
 * Validates required VITE_* environment variables at startup.
 * Fails fast with clear error messages if validation fails.
 *
 * Philosophy:
 * - Single responsibility: Environment validation
 * - Fail fast: Catch configuration errors early
 * - Zero-BS: Clear error messages with actionable guidance
 */

interface EnvConfig {
  VITE_AZURE_CLIENT_ID: string;
  VITE_AZURE_TENANT_ID: string;
  VITE_AZURE_SUBSCRIPTION_ID: string;
  VITE_AZURE_RESOURCE_GROUP?: string;
}

/**
 * GUID format regex for Azure resource IDs
 * Format: 8-4-4-4-12 hexadecimal characters
 */
const GUID_REGEX = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/**
 * Required environment variables that must be set
 */
const REQUIRED_ENV_VARS = [
  'VITE_AZURE_CLIENT_ID',
  'VITE_AZURE_TENANT_ID',
  'VITE_AZURE_SUBSCRIPTION_ID',
] as const;

/**
 * Environment variables that must be valid GUIDs
 */
const GUID_ENV_VARS = [
  'VITE_AZURE_CLIENT_ID',
  'VITE_AZURE_TENANT_ID',
  'VITE_AZURE_SUBSCRIPTION_ID',
] as const;

/**
 * Validate that a value is a valid GUID format
 */
function isValidGuid(value: string): boolean {
  return GUID_REGEX.test(value);
}

/**
 * Validate all required environment variables are set and properly formatted
 * @param env - Optional environment object for testing (defaults to import.meta.env)
 * @throws Error if any required variables are missing or invalid
 */
export function validateEnv(env: Record<string, string | undefined> = import.meta.env): EnvConfig {
  const missing: string[] = [];
  const invalidFormat: Array<{name: string, value: string}> = [];
  const config: Partial<EnvConfig> = {};

  // Check required variables exist
  for (const varName of REQUIRED_ENV_VARS) {
    const value = env[varName];

    if (!value || value.trim().length === 0) {
      missing.push(varName);
    } else {
      config[varName] = value;
    }
  }

  // Check GUID format for Azure IDs
  for (const varName of GUID_ENV_VARS) {
    const value = env[varName];
    if (value && value.trim().length > 0 && !isValidGuid(value)) {
      invalidFormat.push({name: varName, value});
    }
  }

  // Check optional VITE_AZURE_RESOURCE_GROUP if present
  const resourceGroup = env['VITE_AZURE_RESOURCE_GROUP'];
  if (resourceGroup && resourceGroup.trim().length > 0) {
    config.VITE_AZURE_RESOURCE_GROUP = resourceGroup;
  }

  // Build error message if there are issues
  const errors: string[] = [];

  if (missing.length > 0) {
    errors.push(`
Missing required environment variables:
${missing.map(v => `  - ${v}`).join('\n')}

To fix this:
1. Copy .env.example to .env
2. Fill in the required values:
   - VITE_AZURE_CLIENT_ID: Your Azure AD Application (client) ID
   - VITE_AZURE_TENANT_ID: Your Azure AD Directory (tenant) ID
   - VITE_AZURE_SUBSCRIPTION_ID: Your Azure subscription ID

3. Restart the development server

See README.md for detailed setup instructions.
    `.trim());
  }

  if (invalidFormat.length > 0) {
    errors.push(`
Invalid format for Azure environment variables:
${invalidFormat.map(({name, value}) => `  - ${name}: "${value}" is not a valid GUID`).join('\n')}

Azure IDs must be valid GUIDs in the format:
  xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx

Example valid GUID:
  a1b2c3d4-e5f6-7890-abcd-ef1234567890

To fix this:
1. Check your Azure Portal for the correct IDs
2. Ensure they match the GUID format (8-4-4-4-12 hexadecimal characters)
3. Update your .env file with the correct values
4. Restart the development server
    `.trim());
  }

  if (errors.length > 0) {
    throw new Error(errors.join('\n\n'));
  }

  return config as EnvConfig;
}

/**
 * Get validated environment configuration
 * Call this once at application startup
 */
export function getEnvConfig(): EnvConfig {
  return validateEnv();
}

export default validateEnv;
