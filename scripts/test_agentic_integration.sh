#!/usr/bin/env bash
#
# Real Azure Integration Tests for Agentic "azlin do" Command
#
# Prerequisites:
#   1. ANTHROPIC_API_KEY environment variable set
#   2. Azure CLI authenticated (az login)
#   3. azlin configured with resource group
#
# Usage:
#   export ANTHROPIC_API_KEY=your-key-here
#   ./scripts/test_agentic_integration.sh
#

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test VM name
TEST_VM_NAME="azlin-agentic-test-$(date +%s)"
LOG_FILE="/tmp/azlin-agentic-test-$(date +%s).log"

# Track test results
TESTS_PASSED=0
TESTS_FAILED=0
TEST_ERRORS=()

# Logging functions
log_info() {
    echo -e "${GREEN}[INFO]${NC} $1" | tee -a "$LOG_FILE"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1" | tee -a "$LOG_FILE"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1" | tee -a "$LOG_FILE"
}

# Test execution wrapper
run_test() {
    local test_name="$1"
    local test_command="$2"

    log_info "Running test: $test_name"
    echo "Command: $test_command" >> "$LOG_FILE"

    if eval "$test_command" >> "$LOG_FILE" 2>&1; then
        log_info "✅ PASSED: $test_name"
        ((TESTS_PASSED++))
        return 0
    else
        log_error "❌ FAILED: $test_name"
        ((TESTS_FAILED++))
        TEST_ERRORS+=("$test_name")
        return 1
    fi
}

# Pre-flight checks
preflight_checks() {
    log_info "Running pre-flight checks..."

    # Check ANTHROPIC_API_KEY
    if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
        log_error "ANTHROPIC_API_KEY environment variable not set"
        log_error "Set it with: export ANTHROPIC_API_KEY=your-key-here"
        exit 1
    fi
    log_info "✓ ANTHROPIC_API_KEY is set"

    # Check Azure CLI
    if ! command -v az &> /dev/null; then
        log_error "Azure CLI (az) not found"
        exit 1
    fi
    log_info "✓ Azure CLI found"

    # Check Azure authentication
    if ! az account show &> /dev/null; then
        log_error "Not authenticated with Azure. Run: az login"
        exit 1
    fi
    log_info "✓ Azure CLI authenticated"

    # Check azlin installation
    if ! command -v azlin &> /dev/null && [ ! -f "src/azlin/cli.py" ]; then
        log_error "azlin not found. Run from project root or install azlin"
        exit 1
    fi
    log_info "✓ azlin available"

    # Activate venv if exists
    if [ -f "/Users/ryan/src/azlin/.venv/bin/activate" ]; then
        source "/Users/ryan/src/azlin/.venv/bin/activate"
        log_info "✓ Virtual environment activated"
    fi

    log_info "All pre-flight checks passed!\n"
}

# Test 1: Dry-run - List VMs
test_dry_run_list() {
    run_test "Dry-run: List VMs" \
        "python -m azlin.cli do 'list all my vms' --dry-run --verbose"
}

# Test 2: Dry-run - VM Status
test_dry_run_status() {
    run_test "Dry-run: Check VM status" \
        "python -m azlin.cli do 'what is the status of my vms' --dry-run --verbose"
}

# Test 3: Dry-run - Create VM
test_dry_run_create() {
    run_test "Dry-run: Create VM" \
        "python -m azlin.cli do 'create a new vm called $TEST_VM_NAME' --dry-run --verbose"
}

# Test 4: REAL - List VMs
test_real_list_vms() {
    run_test "Real: List VMs" \
        "python -m azlin.cli do 'show me all my vms' --yes --verbose"
}

# Test 5: REAL - Cost Query
test_real_cost_query() {
    run_test "Real: Cost query" \
        "python -m azlin.cli do 'what are my azure costs' --yes --verbose"
}

# Test 6: REAL - Create VM (OPTIONAL - costs money)
test_real_create_vm() {
    if [ "${SKIP_VM_CREATION:-}" = "1" ]; then
        log_warn "Skipping VM creation test (SKIP_VM_CREATION=1)"
        return 0
    fi

    log_warn "This test will CREATE a REAL VM in Azure (costs apply)"
    read -p "Continue? [y/N] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        log_info "Skipping VM creation test"
        return 0
    fi

    run_test "Real: Create VM" \
        "python -m azlin.cli do 'create a new vm called $TEST_VM_NAME' --yes --verbose"

    # Give it time to provision
    log_info "Waiting 30 seconds for VM to provision..."
    sleep 30
}

# Test 7: REAL - VM Status (if created)
test_real_vm_status() {
    if [ "${SKIP_VM_CREATION:-}" = "1" ]; then
        log_warn "Skipping VM status test (no VM created)"
        return 0
    fi

    run_test "Real: Check created VM status" \
        "python -m azlin.cli do 'show me the status of vm $TEST_VM_NAME' --yes --verbose"
}

# Test 8: REAL - Delete VM (cleanup)
test_real_delete_vm() {
    if [ "${SKIP_VM_CREATION:-}" = "1" ]; then
        log_warn "Skipping VM deletion test (no VM created)"
        return 0
    fi

    log_info "Cleaning up: Deleting test VM"
    run_test "Real: Delete test VM" \
        "python -m azlin.cli do 'delete the vm called $TEST_VM_NAME' --yes --verbose"
}

# Test 9: Error Handling - Invalid Request
test_error_handling() {
    log_info "Testing error handling with invalid request"
    # This should succeed (exit 0) but with 0% confidence and no commands executed
    if python -m azlin.cli do "make me coffee" --yes --verbose >> "$LOG_FILE" 2>&1; then
        # Check log to verify 0 commands were executed
        if grep -q "Confidence: 0.0%" "$LOG_FILE" | tail -20; then
            log_info "✅ PASSED: Error handling - invalid request (gracefully handled)"
            ((TESTS_PASSED++))
            return 0
        else
            log_error "Invalid request succeeded but should have had 0% confidence"
            ((TESTS_FAILED++))
            TEST_ERRORS+=("Error handling - invalid request")
            return 1
        fi
    else
        log_error "Invalid request failed (should gracefully succeed with 0% confidence)"
        ((TESTS_FAILED++))
        TEST_ERRORS+=("Error handling - invalid request")
        return 1
    fi
}

# Test 10: Ambiguous Request
test_ambiguous_request() {
    run_test "Ambiguous request handling" \
        "python -m azlin.cli do 'update something' --yes --dry-run --verbose"
}

# Print test summary
print_summary() {
    echo
    echo "========================================"
    echo "INTEGRATION TEST SUMMARY"
    echo "========================================"
    echo "Total tests passed: $TESTS_PASSED"
    echo "Total tests failed: $TESTS_FAILED"
    echo

    if [ $TESTS_FAILED -gt 0 ]; then
        echo "Failed tests:"
        for error in "${TEST_ERRORS[@]}"; do
            echo "  - $error"
        done
        echo
    fi

    echo "Full log: $LOG_FILE"
    echo "========================================"

    if [ $TESTS_FAILED -eq 0 ]; then
        log_info "🎉 ALL TESTS PASSED!"
        return 0
    else
        log_error "❌ Some tests failed. Review log for details."
        return 1
    fi
}

# Main execution
main() {
    log_info "Starting azlin agentic integration tests..."
    log_info "Test VM name: $TEST_VM_NAME"
    log_info "Log file: $LOG_FILE"
    echo

    # Pre-flight checks
    preflight_checks

    # Run tests
    log_info "===== DRY-RUN TESTS ====="
    test_dry_run_list
    test_dry_run_status
    test_dry_run_create

    echo
    log_info "===== REAL AZURE TESTS ====="
    test_real_list_vms
    test_real_cost_query
    test_error_handling
    test_ambiguous_request

    echo
    log_warn "===== OPTIONAL: VM CREATION TESTS ====="
    log_warn "These tests will create and delete a real VM (costs apply)"
    log_warn "Set SKIP_VM_CREATION=1 to skip these tests"
    echo
    test_real_create_vm
    test_real_vm_status
    test_real_delete_vm

    echo
    print_summary
}

# Run main with trap for cleanup
trap 'log_error "Script interrupted"; exit 130' INT TERM

main "$@"
