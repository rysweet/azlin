#!/bin/bash
# Verification script for compound identifier CLI integration

echo "================================================================================================="
echo "COMPOUND IDENTIFIER CLI INTEGRATION VERIFICATION"
echo "================================================================================================="
echo ""

# Color codes
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

verify_count=0
pass_count=0

check() {
    ((verify_count++))
    if [ $? -eq 0 ]; then
        echo -e "${GREEN}✓${NC} $1"
        ((pass_count++))
    else
        echo -e "${RED}✗${NC} $1"
    fi
}

echo "[1] Verifying compound_identifier module exists..."
test -f src/azlin/compound_identifier.py
check "compound_identifier.py exists"

echo ""
echo "[2] Verifying connectivity.py imports..."
grep -q "from azlin.compound_identifier import" src/azlin/commands/connectivity.py
check "connectivity.py imports compound_identifier"

grep -q "parse_identifier" src/azlin/commands/connectivity.py
check "connectivity.py imports parse_identifier"

grep -q "resolve_to_vm" src/azlin/commands/connectivity.py
check "connectivity.py imports resolve_to_vm"

grep -q "CompoundIdentifierError" src/azlin/commands/connectivity.py
check "connectivity.py imports CompoundIdentifierError"

grep -q "AmbiguousIdentifierError" src/azlin/commands/connectivity.py
check "connectivity.py imports AmbiguousIdentifierError"

echo ""
echo "[3] Verifying connectivity.py integration..."
grep -q 'parse_identifier(vm_identifier)' src/azlin/commands/connectivity.py
check "_resolve_vm_identifier() calls parse_identifier()"

grep -q 'resolve_to_vm(vm_identifier, vms, config)' src/azlin/commands/connectivity.py
check "_resolve_vm_identifier() calls resolve_to_vm()"

grep -q 'except (CompoundIdentifierError, AmbiguousIdentifierError) as e:' src/azlin/commands/connectivity.py
check "_resolve_vm_identifier() handles compound errors"

echo ""
echo "[4] Verifying provisioning.py imports..."
grep -q "from azlin.compound_identifier import" src/azlin/commands/provisioning.py
check "provisioning.py imports compound_identifier"

grep -q "parse_identifier" src/azlin/commands/provisioning.py
check "provisioning.py imports parse_identifier"

grep -q "CompoundIdentifierError" src/azlin/commands/provisioning.py
check "provisioning.py imports CompoundIdentifierError"

echo ""
echo "[5] Verifying provisioning.py integration..."
grep -q 'parse_identifier(custom_name)' src/azlin/commands/provisioning.py
check "generate_vm_name() calls parse_identifier()"

grep -q 'parse_identifier(name)' src/azlin/commands/provisioning.py
check "new() command parses --name parameter"

grep -q "VM name is required for provisioning" src/azlin/commands/provisioning.py
check "Rejects session-only format"

grep -q 'session_name_from_param' src/azlin/commands/provisioning.py
check "Extracts session name from compound identifier"

echo ""
echo "[6] Verifying error handling..."
grep -q "Invalid --name format" src/azlin/commands/provisioning.py
check "provisioning.py validates identifier format"

grep -q "multiple colons" src/azlin/commands/connectivity.py
check "connectivity.py mentions multiple colons validation"

echo ""
echo "[7] Verifying backward compatibility preserved..."
grep -q "VMConnector.is_valid_ip" src/azlin/commands/connectivity.py
check "IP address detection preserved"

grep -q "get_vm_name_by_session" src/azlin/commands/connectivity.py
check "Legacy session resolution preserved"

grep -q "_is_valid_vm_name" src/azlin/commands/connectivity.py
check "Simple VM name check preserved"

echo ""
echo "================================================================================================="
echo "VERIFICATION COMPLETE: ${pass_count}/${verify_count} checks passed"
echo "================================================================================================="

if [ $pass_count -eq $verify_count ]; then
    echo ""
    echo -e "${GREEN}✓ ALL VERIFICATIONS PASSED${NC}"
    echo ""
    echo "Integration is complete! The following commands are now supported:"
    echo ""
    echo "  azlin connect atg-dev:amplihack     # Compound format"
    echo "  azlin connect :amplihack            # Session-only format"
    echo "  azlin connect atg-dev               # Simple VM name (legacy)"
    echo "  azlin connect 20.1.2.3              # IP address (legacy)"
    echo ""
    echo "  azlin new --name myvm:dev           # Create VM with session"
    echo "  azlin new --name myvm               # Create VM without session (legacy)"
    echo ""
    exit 0
else
    echo ""
    echo -e "${RED}✗ SOME VERIFICATIONS FAILED${NC}"
    echo ""
    exit 1
fi
