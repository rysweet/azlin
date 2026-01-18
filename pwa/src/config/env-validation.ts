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
}

/**
 * Required environment variables that must be set
 */
const REQUIRED_ENV_VARS = [
  'VITE_AZURE_CLIENT_ID',
  'VITE_AZURE_TENANT_ID',
  'VITE_AZURE_SUBSCRIPTION_ID',
] as const;

/**
 * Validate all required environment variables are set
 * @throws Error if any required variables are missing
 */
export function validateEnv(): EnvConfig {
  const missing: string[] = [];
  const config: Partial<EnvConfig> = {};

  for (const varName of REQUIRED_ENV_VARS) {
    const value = import.meta.env[varName];

    if (!value || value.trim().length === 0) {
      missing.push(varName);
    } else {
      config[varName] = value;
    }
  }

  if (missing.length > 0) {
    const errorMessage = `
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
    `.trim();

    throw new Error(errorMessage);
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
