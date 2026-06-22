#!/usr/bin/env bash
#
# Validate GitHub Actions workflows before pushing
#
# Usage: .github/validate_workflows.sh

set -euo pipefail

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "🔍 Validating GitHub Actions workflows..."
echo ""

# Check if required tools are available
check_tool() {
    if ! command -v "$1" &> /dev/null; then
        echo -e "${YELLOW}⚠️  $1 not found (optional)${NC}"
        return 1
    fi
    return 0
}

# Validate YAML syntax
validate_yaml() {
    local file=$1
    echo -n "Checking $file... "

    if python3 -c "import yaml; yaml.safe_load(open('$file'))" 2>/dev/null; then
        echo -e "${GREEN}✅ Valid${NC}"
        return 0
    else
        echo -e "${RED}❌ Invalid YAML${NC}"
        return 1
    fi
}

# Track validation status
VALIDATION_FAILED=0

# Validate workflow files
echo "📋 Validating YAML syntax:"
validate_yaml ".github/workflows/ci.yml" || VALIDATION_FAILED=1
validate_yaml ".github/workflows/security.yml" || VALIDATION_FAILED=1
validate_yaml ".github/dependabot.yml" || VALIDATION_FAILED=1
echo ""

# Check for required files
echo "📁 Checking required files:"
REQUIRED_FILES=(
    ".github/workflows/ci.yml"
    ".github/workflows/security.yml"
    ".github/workflows/README.md"
    ".github/dependabot.yml"
    ".github/CICD_SETUP.md"
)

for file in "${REQUIRED_FILES[@]}"; do
    if [[ -f "$file" ]]; then
        echo -e "${GREEN}✅${NC} $file"
    else
        echo -e "${RED}❌${NC} $file (missing)"
        VALIDATION_FAILED=1
    fi
done
echo ""

# Check Python version in workflows
echo "🐍 Checking Python versions:"
if grep -q "python-version.*3.13" .github/workflows/ci.yml; then
    echo -e "${GREEN}✅${NC} Python 3.13 support configured"
else
    echo -e "${YELLOW}⚠️${NC}  Python 3.13 not found in CI workflow"
fi

if grep -q "3.11.*3.12.*3.13" .github/workflows/ci.yml; then
    echo -e "${GREEN}✅${NC} Multiple Python versions in test matrix"
else
    echo -e "${YELLOW}⚠️${NC}  Single Python version in test matrix"
fi
echo ""

# Check for coverage configuration
echo "📊 Checking coverage configuration:"
if grep -q "pytest-cov" pyproject.toml; then
    echo -e "${GREEN}✅${NC} pytest-cov in dependencies"
else
    echo -e "${RED}❌${NC} pytest-cov not in dependencies"
    VALIDATION_FAILED=1
fi

if grep -q "THRESHOLD=80" .github/workflows/ci.yml; then
    echo -e "${GREEN}✅${NC} 80% coverage threshold configured"
else
    echo -e "${YELLOW}⚠️${NC}  Coverage threshold not set to 80%"
fi
echo ""

# Check for security scans
echo "🔒 Checking security scans:"
SECURITY_TOOLS=("gitguardian" "bandit" "safety" "codeql")
for tool in "${SECURITY_TOOLS[@]}"; do
    if grep -qi "$tool" .github/workflows/security.yml; then
        echo -e "${GREEN}✅${NC} $tool configured"
    else
        echo -e "${RED}❌${NC} $tool not found"
        VALIDATION_FAILED=1
    fi
done
echo ""

# Check for caching
echo "💾 Checking caching configuration:"
if grep -q "actions/cache@v4" .github/workflows/ci.yml; then
    echo -e "${GREEN}✅${NC} Cache action configured"
else
    echo -e "${YELLOW}⚠️${NC}  No caching found"
fi

if grep -q "enable-cache: true" .github/workflows/ci.yml; then
    echo -e "${GREEN}✅${NC} UV cache enabled"
else
    echo -e "${YELLOW}⚠️${NC}  UV cache not enabled"
fi
echo ""

# Check for best practices
echo "✨ Checking best practices:"
if grep -q "concurrency:" .github/workflows/ci.yml; then
    echo -e "${GREEN}✅${NC} Concurrency control configured"
else
    echo -e "${YELLOW}⚠️${NC}  No concurrency control"
fi

if grep -q "timeout-minutes:" .github/workflows/ci.yml; then
    echo -e "${GREEN}✅${NC} Timeouts configured"
else
    echo -e "${YELLOW}⚠️${NC}  No timeouts set"
fi

if grep -q "fail-fast: false" .github/workflows/ci.yml; then
    echo -e "${GREEN}✅${NC} Non-fail-fast strategy for matrix"
else
    echo -e "${YELLOW}⚠️${NC}  Fail-fast enabled (may hide issues)"
fi
echo ""

# Optional: Check with actionlint if available
if check_tool "actionlint"; then
    echo "🔧 Running actionlint:"
    if actionlint .github/workflows/*.yml 2>&1 | grep -v "shellcheck is not available"; then
        echo -e "${GREEN}✅${NC} actionlint passed"
    fi
    echo ""
fi

# Summary
echo "═══════════════════════════════════════════════════════"
if [[ $VALIDATION_FAILED -eq 0 ]]; then
    echo -e "${GREEN}✅ All validations passed!${NC}"
    echo ""
    echo "Next steps:"
    echo "1. git add .github/"
    echo "2. git commit -m 'ci: Add GitHub Actions workflows'"
    echo "3. git push"
    echo "4. Create PR and verify workflows run"
    exit 0
else
    echo -e "${RED}❌ Some validations failed${NC}"
    echo ""
    echo "Please fix the issues above before pushing."
    exit 1
fi
