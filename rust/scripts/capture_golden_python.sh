#!/bin/bash
# Capture golden file outputs from the Python azlin for comparison with Rust.
# Usage: ./scripts/capture_golden_python.sh [resource-group]
set -euo pipefail
RG="${1:-RYSWEET-LINUX-VM-POOL}"
P="uv run azlin"

mkdir -p tests/golden_python
echo "Capturing Python golden files for RG=$RG..."

$P --version > tests/golden_python/version.txt 2>&1 || true
$P --help > tests/golden_python/help.txt 2>&1 || true
$P list --no-tmux --resource-group "$RG" > tests/golden_python/list.txt 2>&1 || true
$P list --no-tmux --resource-group "$RG" --wide > tests/golden_python/list_wide.txt 2>&1 || true
$P list --no-tmux --resource-group "$RG" --output json > tests/golden_python/list.json 2>&1 || true
$P list --no-tmux --resource-group "$RG" --output csv > tests/golden_python/list.csv 2>&1 || true
$P show devo --resource-group "$RG" > tests/golden_python/show.txt 2>&1 || true
$P health --vm devo --resource-group "$RG" > tests/golden_python/health.txt 2>&1 || true
$P tag list devo --resource-group "$RG" > tests/golden_python/tag_list.txt 2>&1 || true
$P config show > tests/golden_python/config.txt 2>&1 || true

echo "Python golden files captured in tests/golden_python/"
ls -la tests/golden_python/
