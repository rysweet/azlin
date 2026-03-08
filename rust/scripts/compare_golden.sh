#!/bin/bash
# Compare Python vs Rust golden file outputs.
# Usage: ./scripts/compare_golden.sh
# Requires: tests/golden/ (Rust) and tests/golden_python/ (Python)
set -euo pipefail

RUST_DIR="tests/golden"
PY_DIR="tests/golden_python"
DIFF_DIR="tests/golden_diff"

if [ ! -d "$RUST_DIR" ]; then echo "Run ./scripts/capture_golden.sh first"; exit 1; fi
if [ ! -d "$PY_DIR" ]; then echo "Run ./scripts/capture_golden_python.sh first"; exit 1; fi

mkdir -p "$DIFF_DIR"
total=0
diffs=0

for f in "$RUST_DIR"/*; do
    name=$(basename "$f")
    py_file="$PY_DIR/$name"
    total=$((total + 1))

    if [ ! -f "$py_file" ]; then
        echo "SKIP $name (no Python output)"
        continue
    fi

    # Strip ANSI codes and normalize whitespace for comparison
    rust_clean=$(sed 's/\x1b\[[0-9;]*m//g' "$f" | sed 's/[[:space:]]*$//')
    py_clean=$(sed 's/\x1b\[[0-9;]*m//g' "$py_file" | sed 's/[[:space:]]*$//')

    if diff <(echo "$rust_clean") <(echo "$py_clean") > "$DIFF_DIR/$name.diff" 2>&1; then
        echo "MATCH $name"
        rm -f "$DIFF_DIR/$name.diff"
    else
        echo "DIFF  $name  (see $DIFF_DIR/$name.diff)"
        diffs=$((diffs + 1))
    fi
done

echo ""
echo "Results: $total files compared, $diffs differences found"
if [ "$diffs" -gt 0 ]; then
    echo "Review diffs in $DIFF_DIR/"
fi
