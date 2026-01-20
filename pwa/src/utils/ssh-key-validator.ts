/**
 * SSH Key Validation Utility
 *
 * Validates SSH public key format for Azure VM authentication.
 * Supports RSA and Ed25519 key formats.
 *
 * Philosophy:
 * - Single responsibility: SSH key validation
 * - Zero-BS: Real validation logic, no fake checks
 * - Clear error messages for user feedback
 */

export interface SshKeyValidationResult {
  valid: boolean;
  errors: string[];
  keyType?: 'rsa' | 'ed25519' | 'ecdsa';
  keyLength?: number;
}

/**
 * Validate SSH public key format
 *
 * Checks:
 * - Key starts with valid algorithm identifier
 * - Key has valid base64 data
 * - Key meets minimum length requirements
 * - Key format matches SSH public key structure
 *
 * @param sshPublicKey - SSH public key string
 * @returns Validation result with errors if invalid
 */
export function validateSshPublicKey(sshPublicKey: string): SshKeyValidationResult {
  const errors: string[] = [];

  // Trim whitespace
  const key = sshPublicKey.trim();

  // Check if key is empty
  if (!key) {
    return {
      valid: false,
      errors: ['SSH public key is required'],
    };
  }

  // Parse key components
  const parts = key.split(' ');
  if (parts.length < 2) {
    return {
      valid: false,
      errors: ['SSH public key must contain algorithm and key data (e.g., "ssh-rsa AAAA...")'],
    };
  }

  const [algorithm, keyData] = parts;

  // Validate algorithm
  const supportedAlgorithms = ['ssh-rsa', 'ssh-ed25519', 'ecdsa-sha2-nistp256', 'ecdsa-sha2-nistp384', 'ecdsa-sha2-nistp521'];
  if (!supportedAlgorithms.includes(algorithm)) {
    errors.push(`Unsupported algorithm "${algorithm}". Supported: ${supportedAlgorithms.join(', ')}`);
  }

  // Validate key data (base64)
  if (!isValidBase64(keyData)) {
    errors.push('SSH key data is not valid base64 encoding');
  }

  // Check minimum key length (base64 string length)
  const minLengths: Record<string, number> = {
    'ssh-rsa': 350,        // RSA 2048-bit minimum
    'ssh-ed25519': 60,     // Ed25519 keys are shorter
    'ecdsa-sha2-nistp256': 100,
    'ecdsa-sha2-nistp384': 120,
    'ecdsa-sha2-nistp521': 140,
  };

  const minLength = minLengths[algorithm] || 100;
  if (keyData.length < minLength) {
    errors.push(`SSH key appears too short (${keyData.length} chars). Minimum ${minLength} expected for ${algorithm}`);
  }

  // Determine key type
  let keyType: 'rsa' | 'ed25519' | 'ecdsa' | undefined;
  if (algorithm === 'ssh-rsa') {
    keyType = 'rsa';
  } else if (algorithm === 'ssh-ed25519') {
    keyType = 'ed25519';
  } else if (algorithm.startsWith('ecdsa-')) {
    keyType = 'ecdsa';
  }

  // Return validation result
  return {
    valid: errors.length === 0,
    errors,
    keyType,
    keyLength: keyData.length,
  };
}

/**
 * Check if string is valid base64
 */
function isValidBase64(str: string): boolean {
  // Base64 characters: A-Z, a-z, 0-9, +, /, =
  const base64Regex = /^[A-Za-z0-9+/]+={0,2}$/;
  return base64Regex.test(str);
}

/**
 * Extract key comment (optional third part of SSH key)
 *
 * Example: "ssh-rsa AAAA... user@host" -> "user@host"
 */
export function extractSshKeyComment(sshPublicKey: string): string | null {
  const parts = sshPublicKey.trim().split(' ');
  return parts.length >= 3 ? parts.slice(2).join(' ') : null;
}

/**
 * Format SSH key for display (truncate middle)
 *
 * Example: "ssh-rsa AAAA...yz== user@host"
 */
export function formatSshKeyForDisplay(sshPublicKey: string, maxLength: number = 60): string {
  const parts = sshPublicKey.trim().split(' ');
  if (parts.length < 2) return sshPublicKey;

  const [algorithm, keyData, ...comment] = parts;

  if (keyData.length <= maxLength - algorithm.length - 10) {
    return sshPublicKey;
  }

  // Truncate middle of key data
  const visibleChars = maxLength - algorithm.length - 15;
  const prefixChars = Math.floor(visibleChars / 2);
  const suffixChars = visibleChars - prefixChars;

  const truncatedKey = `${keyData.slice(0, prefixChars)}...${keyData.slice(-suffixChars)}`;

  const displayParts = [algorithm, truncatedKey];
  if (comment.length > 0) {
    displayParts.push(comment.join(' '));
  }

  return displayParts.join(' ');
}

export default validateSshPublicKey;
