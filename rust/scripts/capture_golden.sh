#!/bin/bash
# Capture golden file outputs for comparison testing.
# Usage: ./scripts/capture_golden.sh [resource-group]
set -euo pipefail

RG="${1:-RYSWEET-LINUX-VM-POOL}"
RUST="./target/release/azlin"

if [ ! -x "$RUST" ]; then
    echo "ERROR: $RUST not found. Run 'cargo build --release' first." >&2
    exit 1
fi

mkdir -p tests/golden

echo "Capturing golden files with resource group: $RG"

$RUST list --no-tmux --resource-group "$RG" > tests/golden/list.txt 2>&1 || true
$RUST list --no-tmux --resource-group "$RG" --wide > tests/golden/list_wide.txt 2>&1 || true
$RUST list --no-tmux --resource-group "$RG" --output json > tests/golden/list.json 2>&1 || true
$RUST show devo --resource-group "$RG" > tests/golden/show.txt 2>&1 || true
$RUST health --vm devo --resource-group "$RG" > tests/golden/health.txt 2>&1 || true
$RUST --version > tests/golden/version.txt 2>&1
$RUST --help > tests/golden/help.txt 2>&1

echo "Golden files captured in tests/golden/"
ls -la tests/golden/
