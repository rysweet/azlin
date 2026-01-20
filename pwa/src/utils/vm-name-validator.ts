/**
 * VM Name Validation Utility
 *
 * Validates Azure VM naming conventions and reserved names.
 * Azure VM names must follow specific rules for compatibility.
 *
 * Philosophy:
 * - Single responsibility: VM name validation
 * - Zero-BS: Real Azure naming rules
 * - Clear error messages for user guidance
 */

export interface VmNameValidationResult {
  valid: boolean;
  errors: string[];
  suggestions?: string[];
}

/**
 * Validate Azure VM name
 *
 * Azure VM naming rules:
 * - Must be 1-64 characters long
 * - Can contain lowercase letters, numbers, and hyphens
 * - Must start with a letter
 * - Cannot end with a hyphen
 * - No consecutive hyphens
 * - Cannot use reserved names
 *
 * @param vmName - Proposed VM name
 * @returns Validation result with errors and suggestions
 */
export function validateVmName(vmName: string): VmNameValidationResult {
  const errors: string[] = [];
  const suggestions: string[] = [];

  // Trim whitespace
  const name = vmName.trim();

  // Check if name is empty
  if (!name) {
    return {
      valid: false,
      errors: ['VM name is required'],
    };
  }

  // Check length (1-64 characters)
  if (name.length < 1 || name.length > 64) {
    errors.push('VM name must be 1-64 characters long');
    if (name.length > 64) {
      suggestions.push(`Try: ${name.slice(0, 61)}...`);
    }
  }

  // Check if starts with letter
  if (!/^[a-z]/i.test(name)) {
    errors.push('VM name must start with a letter');
    if (/^[0-9]/.test(name)) {
      suggestions.push(`Try: vm-${name}`);
    }
  }

  // Check if ends with hyphen
  if (name.endsWith('-')) {
    errors.push('VM name cannot end with a hyphen');
    suggestions.push(name.slice(0, -1));
  }

  // Check for valid characters (lowercase letters, numbers, hyphens)
  if (!/^[a-z0-9-]+$/.test(name)) {
    errors.push('VM name can only contain lowercase letters, numbers, and hyphens');

    // Suggest lowercase conversion
    const lowercase = name.toLowerCase();
    // Remove invalid characters
    const cleaned = lowercase.replace(/[^a-z0-9-]/g, '-');
    suggestions.push(cleaned);
  }

  // Check for consecutive hyphens
  if (/--/.test(name)) {
    errors.push('VM name cannot contain consecutive hyphens');
    suggestions.push(name.replace(/--+/g, '-'));
  }

  // Check for reserved names
  const reservedNames = [
    'localhost',
    'admin',
    'root',
    'administrator',
    'guest',
    'sys',
    'system',
    'default',
    'azure',
    'microsoft',
  ];

  if (reservedNames.includes(name.toLowerCase())) {
    errors.push(`"${name}" is a reserved name and cannot be used`);
    suggestions.push(`${name}-vm`, `my-${name}`, `${name}-01`);
  }

  // Return validation result
  return {
    valid: errors.length === 0,
    errors,
    suggestions: suggestions.length > 0 ? suggestions : undefined,
  };
}

/**
 * Generate valid VM name from user input
 *
 * Automatically cleans and formats the name to meet Azure requirements.
 *
 * @param input - User input string
 * @returns Valid VM name
 */
export function sanitizeVmName(input: string): string {
  let name = input.trim().toLowerCase();

  // Remove invalid characters
  name = name.replace(/[^a-z0-9-]/g, '-');

  // Remove consecutive hyphens
  name = name.replace(/--+/g, '-');

  // Ensure starts with letter
  if (!/^[a-z]/.test(name)) {
    name = `vm-${name}`;
  }

  // Remove trailing hyphens
  name = name.replace(/-+$/, '');

  // Trim to 64 characters
  if (name.length > 64) {
    name = name.slice(0, 64);
    // Remove trailing hyphen if trimming created one
    name = name.replace(/-+$/, '');
  }

  return name;
}

/**
 * Check if VM name is available (format check only, not Azure availability)
 *
 * Note: This only checks format, not actual availability in Azure.
 * Actual availability requires Azure API call.
 */
export function isVmNameFormatValid(vmName: string): boolean {
  const result = validateVmName(vmName);
  return result.valid;
}

export default validateVmName;
