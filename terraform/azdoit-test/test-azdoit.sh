#!/bin/bash
#
# AZDOIT Test Script
#
# Runs comprehensive tests against deployed infrastructure to validate
# azdoit CLI functionality.
#
# Usage:
#   ./test-azdoit.sh
#
# Prerequisites:
#   - Infrastructure deployed via terraform apply
#   - azdoit CLI installed and configured
#   - Azure CLI authenticated

set -e

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Test counters
TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0

# Get resource group name from Terraform output
RESOURCE_GROUP=$(terraform output -raw resource_group_name 2>/dev/null || echo "test-azdoit-rg")
VM_NAME=$(terraform output -raw vm_name 2>/dev/null || echo "test-azdoit-vm-1")

echo "======================================"
echo "AZDOIT Test Suite"
echo "======================================"
echo "Resource Group: $RESOURCE_GROUP"
echo "VM Name: $VM_NAME"
echo "======================================"
echo ""

# Function to run a test
run_test() {
    local test_name="$1"
    local command="$2"
    local expected_exit="$3"  # 0 for success, 1 for failure

    TESTS_RUN=$((TESTS_RUN + 1))
    echo -n "Test $TESTS_RUN: $test_name... "

    if output=$(eval "$command" 2>&1); then
        exit_code=0
    else
        exit_code=$?
    fi

    if [ "$exit_code" -eq "$expected_exit" ]; then
        echo -e "${GREEN}PASSED${NC}"
        TESTS_PASSED=$((TESTS_PASSED + 1))
        if [ -n "$output" ]; then
            echo "  Output: ${output:0:100}..."
        fi
    else
        echo -e "${RED}FAILED${NC}"
        TESTS_FAILED=$((TESTS_FAILED + 1))
        echo "  Expected exit code: $expected_exit"
        echo "  Actual exit code: $exit_code"
        echo "  Output: $output"
    fi
    echo ""
}

# Test 1: List VMs in resource group
run_test "List VMs in resource group" \
    "azdoit 'list VMs in $RESOURCE_GROUP'" \
    0

# Test 2: Get VM details
run_test "Get VM details" \
    "azdoit 'get VM $VM_NAME details'" \
    0

# Test 3: Get VM status
run_test "Get VM power state" \
    "azdoit 'get status of $VM_NAME'" \
    0

# Test 4: List all resources in resource group
run_test "List all resources in resource group" \
    "azdoit 'list all resources in $RESOURCE_GROUP'" \
    0

# Test 5: Get resource group details
run_test "Get resource group details" \
    "azdoit 'show details of $RESOURCE_GROUP'" \
    0

# Test 6: Stop VM (if running)
echo -e "${YELLOW}Starting VM power management tests...${NC}"
run_test "Stop VM" \
    "azdoit 'stop VM $VM_NAME'" \
    0

# Wait for VM to stop
echo "Waiting 30 seconds for VM to stop..."
sleep 30

# Test 7: Verify VM is stopped
run_test "Verify VM is stopped/deallocated" \
    "azdoit 'get status of $VM_NAME'" \
    0

# Test 8: Start VM
run_test "Start VM" \
    "azdoit 'start VM $VM_NAME'" \
    0

# Wait for VM to start
echo "Waiting 30 seconds for VM to start..."
sleep 30

# Test 9: Verify VM is running
run_test "Verify VM is running" \
    "azdoit 'get status of $VM_NAME'" \
    0

# Test 10: Cost estimate
run_test "Get cost estimate for resource group" \
    "azdoit 'show cost estimate for $RESOURCE_GROUP'" \
    0

# Test 11: List network interfaces
run_test "List network interfaces" \
    "azdoit 'list network interfaces in $RESOURCE_GROUP'" \
    0

# Test 12: Query non-existent resource (should handle gracefully)
run_test "Query non-existent VM (error handling)" \
    "azdoit 'get VM non-existent-vm-12345 details'" \
    1

echo "======================================"
echo "Test Results"
echo "======================================"
echo "Total tests run: $TESTS_RUN"
echo -e "Tests passed: ${GREEN}$TESTS_PASSED${NC}"
echo -e "Tests failed: ${RED}$TESTS_FAILED${NC}"
echo "======================================"

if [ "$TESTS_FAILED" -eq 0 ]; then
    echo -e "${GREEN}All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}Some tests failed. Please review output above.${NC}"
    exit 1
fi
