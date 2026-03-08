#!/bin/bash
# compare-all.sh — Run parity comparison for all commands that work without Azure
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPORT_DIR="${REPORT_DIR:-outputs/compare}"
mkdir -p "$REPORT_DIR"

COMMANDS=(
    "--help"
    "--version"
    "list --help"
    "start --help"
    "stop --help"
    "connect --help"
    "delete --help"
    "env --help"
    "snapshot --help"
    "storage --help"
    "keys --help"
    "cost --help"
    "auth --help"
    "batch --help"
    "fleet --help"
    "compose --help"
    "health --help"
    "bastion --help"
    "new --help"
    "doit --help"
    "ask --help"
    "template --help"
    "context --help"
    "sessions --help"
    "disk --help"
    "ip --help"
    "github-runner --help"
    "autopilot --help"
)

PASS=0
FAIL=0
TOTAL=${#COMMANDS[@]}

echo "Running $TOTAL parity comparisons..."
echo

for cmd in "${COMMANDS[@]}"; do
    echo "━━━ azlin $cmd ━━━"
    "$SCRIPT_DIR/compare.sh" $cmd 2>&1 | grep -E "✓|✗|⚡|Exit code"
    if [ ${PIPESTATUS[0]} -eq 0 ]; then
        ((PASS++))
    else
        ((FAIL++))
    fi
    echo
done

echo "╔══════════════════════════════════════╗"
echo "║  SUMMARY: $PASS/$TOTAL passed         ║"
echo "╚══════════════════════════════════════╝"
