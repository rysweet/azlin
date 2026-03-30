#!/usr/bin/env bash
# Validates TESTING.md accuracy against the actual codebase.
# Catches documentation drift — run after adding/removing tests.
#
# Usage: ./scripts/test_testing_docs.sh
# Exit code: 0 = all checks pass, 1 = drift detected

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TESTING_MD="$REPO_ROOT/TESTING.md"
PASS=0
FAIL=0

pass() { ((PASS++)) || true; echo "  ✅ $1"; }
fail() { ((FAIL++)) || true; echo "  ❌ $1"; }

echo "=== TESTING.md Documentation Validation ==="
echo ""

# ─── Section 1: File exists ──────────────────────────────────────────────
echo "1. File existence"
if [[ -f "$TESTING_MD" ]]; then
    pass "TESTING.md exists"
else
    fail "TESTING.md not found at repo root"
fi

# Read file once — eliminates ~50 grep subprocess spawns
TESTING_CONTENT=$(<"$TESTING_MD")

# ─── Section 2: Required sections present ─────────────────────────────────
echo "2. Required sections"
required_sections=(
    "Quick Start"
    "Test Categories"
    "Rust Unit Tests"
    "Rust Integration Tests"
    "Live Azure Tests"
    "Agentic Scenario Tests"
    "Agentic Integration Shell Tests"
    "E2E Tests"
    "Benchmarks"
    "Environment Variables"
    "Linting"
    "Test Coverage"
    "CI Pipeline"
    "Detailed Documentation"
    "Prerequisites"
)
for section in "${required_sections[@]}"; do
    if [[ "$TESTING_CONTENT" == *"## ${section}"* || "$TESTING_CONTENT" == *"### ${section}"* ]]; then
        pass "Section: $section"
    else
        fail "Missing section: $section"
    fi
done

# ─── Section 3: Unit test group count ─────────────────────────────────────
echo "3. Unit test group counts"
actual_unit=$(find "$REPO_ROOT/rust/crates/azlin/src/tests" -name '*.rs' -not -name 'mod.rs' | wc -l)
doc_unit=$(grep -oP '\d+ test groups.*tests/' <<< "$TESTING_CONTENT" | head -1 | grep -oP '^\d+' || true)
if [[ -z "$doc_unit" ]]; then
    fail "Unit test groups: could not extract count from TESTING.md"
elif [[ "$actual_unit" -eq "$doc_unit" ]]; then
    pass "Unit test groups: doc=$doc_unit, actual=$actual_unit"
else
    fail "Unit test groups: doc=$doc_unit, actual=$actual_unit"
fi

# ─── Section 4: Handler test group count ──────────────────────────────────
echo "4. Handler test group counts"
actual_handler=$(find "$REPO_ROOT/rust/crates/azlin/src/handlers/tests" -name '*.rs' -not -name 'mod.rs' | wc -l)
doc_handler=$(grep -oP '\d+ handler test groups' <<< "$TESTING_CONTENT" | grep -oP '^\d+' || true)
if [[ -z "$doc_handler" ]]; then
    fail "Handler test groups: could not extract count from TESTING.md"
elif [[ "$actual_handler" -eq "$doc_handler" ]]; then
    pass "Handler test groups: doc=$doc_handler, actual=$actual_handler"
else
    fail "Handler test groups: doc=$doc_handler, actual=$actual_handler"
fi

# ─── Section 5: Integration test file count ───────────────────────────────
echo "5. Integration test file count"
actual_integ=$(find "$REPO_ROOT/rust/crates/azlin/tests" -maxdepth 1 -name '*.rs' | wc -l)
doc_integ=$(grep -oP '\d+ test files in' <<< "$TESTING_CONTENT" | grep -oP '^\d+' || true)
if [[ -z "$doc_integ" ]]; then
    fail "Integration test files: could not extract count from TESTING.md"
elif [[ "$actual_integ" -eq "$doc_integ" ]]; then
    pass "Integration test files: doc=$doc_integ, actual=$actual_integ"
else
    fail "Integration test files: doc=$doc_integ, actual=$actual_integ"
fi

# ─── Section 6: Every integration test file listed in the table ───────────
echo "6. Integration test files listed in table"
for rs_file in "$REPO_ROOT"/rust/crates/azlin/tests/*.rs; do
    basename_rs=$(basename "$rs_file")
    if [[ "$TESTING_CONTENT" == *"$basename_rs"* ]]; then
        pass "Listed: $basename_rs"
    else
        fail "Not listed in table: $basename_rs"
    fi
done

# ─── Section 7: Cross-referenced docs exist ───────────────────────────────
echo "7. Cross-referenced documents"
linked_docs=(
    "docs/TEST_SUITE_SPECIFICATION.md"
    "docs/AGENTIC_INTEGRATION_TESTS.md"
    "docs/REAL_AZURE_TESTING.md"
    "benchmarks/README.md"
    "docs/testing/test_plan.md"
    "docs/testing/test_strategy.md"
    "docs/testing/TDD_RED_PHASE_COMPLETE.md"
    "docs/testing/backup-dr-test-coverage.md"
)
for doc in "${linked_docs[@]}"; do
    if [[ -f "$REPO_ROOT/$doc" ]]; then
        pass "Exists: $doc"
    else
        fail "Missing: $doc"
    fi
done

# ─── Section 8: Agentic scenario YAML files referenced ───────────────────
echo "8. Agentic scenario files"
scenarios=(
    "ssh-identity-key.yaml"
    "new-command-parity.yaml"
)
for scenario in "${scenarios[@]}"; do
    if [[ -f "$REPO_ROOT/tests/agentic-scenarios/$scenario" ]]; then
        pass "Scenario exists: $scenario"
    else
        fail "Scenario missing: $scenario"
    fi
    if [[ "$TESTING_CONTENT" == *"$scenario"* ]]; then
        pass "Scenario documented: $scenario"
    else
        fail "Scenario not documented: $scenario"
    fi
done

# ─── Section 9: Agentic shell test function count ─────────────────────────
echo "9. Agentic integration shell test count"
actual_agentic=$(grep -c '^test_' "$REPO_ROOT/scripts/test_agentic_integration.sh" || true)
doc_agentic=$(grep -oP 'runs \d+ agentic tests' <<< "$TESTING_CONTENT" | grep -oP '\d+' || true)
if [[ -z "$doc_agentic" || -z "$actual_agentic" ]]; then
    fail "Agentic test functions: could not extract counts (doc=$doc_agentic, actual=$actual_agentic)"
elif [[ "$actual_agentic" -eq "$doc_agentic" ]]; then
    pass "Agentic test functions: doc=$doc_agentic, actual=$actual_agentic"
else
    fail "Agentic test functions: doc=$doc_agentic, actual=$actual_agentic"
fi

# ─── Section 10: Every agentic shell test function listed ─────────────────
echo "10. Agentic test functions listed"
while IFS= read -r fn; do
    if [[ "$TESTING_CONTENT" == *"$fn"* ]]; then
        pass "Listed: $fn"
    else
        fail "Not listed: $fn"
    fi
done < <(grep -oP '^test_\w+' "$REPO_ROOT/scripts/test_agentic_integration.sh")

# ─── Section 11: E2E test files ──────────────────────────────────────────
echo "11. E2E test files"
if [[ -f "$REPO_ROOT/tests/e2e/test_restore_multi_session.yaml" ]]; then
    pass "E2E scenario exists: test_restore_multi_session.yaml"
else
    fail "E2E scenario missing: test_restore_multi_session.yaml"
fi
if [[ "$TESTING_CONTENT" == *"test_restore_multi_session"* ]]; then
    pass "E2E scenario documented"
else
    fail "E2E scenario not documented"
fi

# ─── Section 12: Environment variables documented ─────────────────────────
echo "12. Environment variables"
env_vars=(
    "RUST_MIN_STACK"
    "AZLIN_BIN"
    "AZLIN_TEST_MODE"
    "ANTHROPIC_API_KEY"
    "AZURE_SUBSCRIPTION_ID"
    "AZURE_TENANT_ID"
)
for var in "${env_vars[@]}"; do
    if [[ "$TESTING_CONTENT" == *"$var"* ]]; then
        pass "Env var documented: $var"
    else
        fail "Env var missing: $var"
    fi
done

# ─── Section 13: CI workflow file exists ──────────────────────────────────
echo "13. CI workflow"
if [[ -f "$REPO_ROOT/.github/workflows/rust-ci.yml" ]]; then
    pass "rust-ci.yml exists"
else
    fail "rust-ci.yml not found"
fi

# ─── Section 14: Cargo config auto-sets RUST_MIN_STACK ────────────────────
echo "14. Cargo config"
if grep -q "RUST_MIN_STACK" "$REPO_ROOT/rust/.cargo/config.toml" 2>/dev/null; then
    pass "RUST_MIN_STACK set in .cargo/config.toml"
else
    fail "RUST_MIN_STACK not found in .cargo/config.toml"
fi

# ─── Summary ──────────────────────────────────────────────────────────────
echo ""
echo "=== Results: $PASS passed, $FAIL failed ==="
if [[ $FAIL -gt 0 ]]; then
    echo "⚠️  Documentation drift detected — update TESTING.md"
    exit 1
else
    echo "✅ TESTING.md is accurate"
    exit 0
fi
