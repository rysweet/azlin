# GitHub Actions Workflows

This directory contains CI/CD workflows for the azlin project.

## Workflows

### 1. CI (`ci.yml`)

Runs on every push to `main` and on all pull requests.

**Jobs:**
- **Pre-commit Checks** - Runs ruff, formatting, and file hygiene checks
- **Type Checking** - Runs Pyright strict type checking on `src/`
- **Tests** - Runs pytest test suite on Python 3.11, 3.12, and 3.13
  - Unit tests with coverage reporting
  - Uploads coverage to Codecov
  - Test results uploaded as artifacts
- **Coverage Check** - Enforces 80% minimum code coverage
- **Integration Tests** - Runs integration tests on main branch only
- **All Checks** - Summary job that must pass for CI to pass

**Performance Optimizations:**
- Parallel job execution for fast feedback
- Dependency caching (uv, pytest, pre-commit)
- Concurrency controls to cancel outdated runs
- Separate type checking from pre-commit for faster feedback

**Timeouts:**
- Pre-commit: 10 minutes
- Type checking: 10 minutes
- Tests: 30 minutes
- Integration tests: 30 minutes

### 2. Security (`security.yml`)

Runs on:
- Every push to `main`
- All pull requests
- Daily at 2 AM UTC (scheduled scan)
- Manual trigger via workflow_dispatch

**Jobs:**
- **GitGuardian** - Scans for secrets and credentials in code
- **Bandit** - Python security linter (checks for common security issues)
- **Safety** - Checks dependencies for known vulnerabilities
- **CodeQL** - GitHub's advanced security analysis
- **Trivy** - Vulnerability scanner for dependencies
- **OSSF Scorecard** - Project security posture check (main branch only)
- **Security Summary** - Aggregates all security scan results

**Reports:**
All security scan reports are uploaded as artifacts with 90-day retention.

**Failure Policy:**
- GitGuardian failures block PRs (secrets detected)
- Other security tools provide warnings but don't block

### 3. Documentation Validation (`doc-validation.yml`)

Runs on:
- Pull requests that modify documentation or CLI code
- Push to `main` or `develop` branches
- Manual trigger via workflow_dispatch

**Jobs:**
- **Validate Documentation** - Checks consistency between CLI and documentation

**What it validates:**
- All CLI commands are documented in README.md
- No documentation for non-existent commands
- Command options match between CLI and docs
- Examples use correct command syntax

**Performance:**
- Fast execution: < 30 seconds
- Minimal dependencies (only Click required)
- Shallow git clone for speed
- Caches pip packages

**Failure Conditions:**
- CLI commands missing from documentation
- Documentation references removed commands
- Invalid command examples in docs

**When triggered:**
Automatically runs when PRs touch:
- `README.md`
- `docs/**/*.md`
- `src/azlin/cli.py`
- `src/azlin/commands/*.py`

### 4. Dependabot (`dependabot.yml`)

Automated dependency updates:

**Update Schedule:** Weekly on Mondays at 9 AM

**Package Ecosystems:**
- **Python dependencies** - Groups pytest, dev-tools, and Azure packages
- **GitHub Actions** - Keeps workflow actions up to date
- **Pre-commit hooks** - Updates pre-commit hook versions

**PR Limits:**
- Python: 10 PRs max
- GitHub Actions: 5 PRs max
- Pre-commit: 5 PRs max

## Required Secrets

Configure these secrets in GitHub repository settings:

### Optional (Recommended)
- `CODECOV_TOKEN` - For coverage reporting (get from codecov.io)
- `GITGUARDIAN_API_KEY` - For secret scanning (get from gitguardian.com)

## Badge Status

Add these badges to your README.md:

```markdown
![CI](https://github.com/rysweet/azlin/workflows/CI/badge.svg)
![Security](https://github.com/rysweet/azlin/workflows/Security%20Scanning/badge.svg)
[![codecov](https://codecov.io/gh/rysweet/azlin/branch/main/graph/badge.svg)](https://codecov.io/gh/rysweet/azlin)
```

## Local Testing

Test workflows locally before pushing:

```bash
# Install act (GitHub Actions local runner)
brew install act  # macOS
# or
curl https://raw.githubusercontent.com/nektos/act/master/install.sh | sudo bash  # Linux

# Run CI workflow
act pull_request -W .github/workflows/ci.yml

# Run security workflow
act pull_request -W .github/workflows/security.yml

# Run documentation validation
act pull_request -W .github/workflows/doc-validation.yml
```

## Best Practices

1. **Fast Feedback** - Jobs run in parallel where possible
2. **Clear Errors** - Descriptive error messages with emojis
3. **Caching** - Dependencies cached to speed up builds
4. **Reasonable Timeouts** - Prevents hanging jobs
5. **Artifact Retention** - Test results kept for 30 days, security reports for 90 days
6. **Concurrency Control** - Cancels outdated runs to save resources

## Troubleshooting

### CI Failing

**Pre-commit checks fail:**
```bash
# Run locally
pre-commit run --all-files

# Update hooks
pre-commit autoupdate
```

**Type checking fails:**
```bash
# Run locally
pyright src/
```

**Tests fail:**
```bash
# Run specific test
pytest tests/unit/test_specific.py -v

# Run with coverage
pytest tests/unit --cov=src/azlin --cov-report=term-missing
```

**Coverage below 80%:**
```bash
# Generate coverage report
pytest tests/unit --cov=src/azlin --cov-report=html
open htmlcov/index.html  # View uncovered lines
```

**Documentation validation fails:**
```bash
# Run validation locally
python scripts/validate_documentation.py

# Check what commands are in CLI
python -c "from azlin.cli import cli; print([n for n in cli.commands.keys()])"

# See DOCUMENTATION_FIX_PLAN.md for guidance
```

### Security Scan Failing

**GitGuardian detects secrets:**
- Remove secrets from code
- Add to `.gitignore` if they're config files
- Use environment variables or GitHub Secrets
- Consider using `git-filter-repo` to remove from history

**Bandit security issues:**
```bash
# Run locally
bandit -r src/ --severity-level medium
```

**Safety vulnerable dependencies:**
```bash
# Check dependencies
safety check

# Update specific package
uv pip install --upgrade package-name
```

## Updating Workflows

When modifying workflows:

1. Test YAML syntax: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/ci.yml'))"`
2. Validate with `actionlint` (optional): `brew install actionlint && actionlint`
3. Test locally with `act` if possible
4. Create PR and verify checks pass
5. Monitor first run on main branch

## References

- [GitHub Actions Documentation](https://docs.github.com/en/actions)
- [Workflow Syntax](https://docs.github.com/en/actions/using-workflows/workflow-syntax-for-github-actions)
- [Security Hardening](https://docs.github.com/en/actions/security-guides/security-hardening-for-github-actions)
# Trigger CI
