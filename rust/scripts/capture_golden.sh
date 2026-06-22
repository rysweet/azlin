#!/bin/bash
# Capture golden file outputs for side-by-side comparison
# Usage: ./scripts/capture_golden.sh [resource-group]
set -euo pipefail
RG="${1:-RYSWEET-LINUX-VM-POOL}"
R="./target/release/azlin"

mkdir -p tests/golden
echo "Capturing golden files for RG=$RG..."

$R --version > tests/golden/version.txt 2>&1
$R --help > tests/golden/help.txt 2>&1
$R list --no-tmux --resource-group "$RG" > tests/golden/list.txt 2>&1
$R list --no-tmux --resource-group "$RG" --wide > tests/golden/list_wide.txt 2>&1
$R list --no-tmux --resource-group "$RG" --output json > tests/golden/list.json 2>&1
$R list --no-tmux --resource-group "$RG" --output csv > tests/golden/list.csv 2>&1
$R show devo --resource-group "$RG" > tests/golden/show.txt 2>&1
$R health --vm devo --resource-group "$RG" > tests/golden/health.txt 2>&1
$R tag list devo --resource-group "$RG" > tests/golden/tag_list.txt 2>&1
$R config show > tests/golden/config.txt 2>&1

echo "Golden files captured in tests/golden/"
ls -la tests/golden/
