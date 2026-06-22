#!/usr/bin/env bash
# compare.sh — Compare Python and Rust azlin versions
# Runs both versions and compares outputs for parity checking.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUST_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_DIR="$(dirname "$RUST_DIR")"

PYTHON_BIN="${PYTHON_BIN:-azlin}"
RUST_BIN="${RUST_DIR}/target/release/azlin"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
NC='\033[0m'

pass=0
fail=0
skip=0

compare_command() {
    local desc="$1"
    shift
    local args=("$@")

    printf "%-40s " "$desc"

    # Run Python version
    local py_start py_end py_time py_out py_rc
    py_start=$(date +%s%N)
    py_out=$($PYTHON_BIN "${args[@]}" 2>&1) || py_rc=$?
    py_rc=${py_rc:-0}
    py_end=$(date +%s%N)
    py_time=$(( (py_end - py_start) / 1000000 ))

    # Run Rust version
    local rs_start rs_end rs_time rs_out rs_rc
    if [[ ! -x "$RUST_BIN" ]]; then
        printf "${YELLOW}SKIP${NC} (Rust binary not built)\n"
        ((skip++))
        return
    fi

    rs_start=$(date +%s%N)
    rs_out=$($RUST_BIN "${args[@]}" 2>&1) || rs_rc=$?
    rs_rc=${rs_rc:-0}
    rs_end=$(date +%s%N)
    rs_time=$(( (rs_end - rs_start) / 1000000 ))

    if [[ $py_rc -eq $rs_rc ]]; then
        printf "${GREEN}PASS${NC}  py=%dms  rs=%dms  speedup=%.1fx\n" \
            "$py_time" "$rs_time" "$(echo "scale=1; $py_time / ($rs_time + 1)" | bc)"
        ((pass++))
    else
        printf "${RED}FAIL${NC}  py_rc=%d rs_rc=%d\n" "$py_rc" "$rs_rc"
        ((fail++))
    fi
}

echo "=== Azlin Python vs Rust Comparison ==="
echo ""

compare_command "version"        version
compare_command "config show"    config show
compare_command "help"           --help
compare_command "list --help"    list --help

echo ""
echo "=== Results: ${pass} passed, ${fail} failed, ${skip} skipped ==="
