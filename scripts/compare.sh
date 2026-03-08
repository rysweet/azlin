#!/bin/bash
# compare.sh — Core instrument for the parity goal-seeking loop
# Runs the same command against both Python and Rust azlin, compares results.
#
# Usage: ./scripts/compare.sh <command> [args...]
# Example: ./scripts/compare.sh --help
# Example: ./scripts/compare.sh list --help
# Example: ./scripts/compare.sh --version
#
# Set PYTHON_BIN and RUST_BIN to override binary locations.

set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-uv run azlin}"
RUST_BIN="${RUST_BIN:-./rust/target/debug/azlin}"
REPORT_DIR="${REPORT_DIR:-outputs/compare}"

mkdir -p "$REPORT_DIR"

CMD="$*"
LABEL=$(echo "$CMD" | tr ' /' '_-')
TIMESTAMP=$(date +%s)

echo "╔══════════════════════════════════════╗"
echo "║  AZLIN PARITY COMPARISON             ║"
echo "╠══════════════════════════════════════╣"
echo "║  Command: azlin $CMD"
echo "╚══════════════════════════════════════╝"
echo

# Run Python version
echo "▸ Python version..."
PY_START=$(date +%s%N)
PY_OUTPUT=$($PYTHON_BIN $CMD 2>&1) || PY_EXIT=$?
PY_END=$(date +%s%N)
PY_EXIT=${PY_EXIT:-0}
PY_TIME_MS=$(( (PY_END - PY_START) / 1000000 ))
echo "  Exit: $PY_EXIT | Time: ${PY_TIME_MS}ms"

# Run Rust version
echo "▸ Rust version..."
RS_START=$(date +%s%N)
RS_OUTPUT=$($RUST_BIN $CMD 2>&1) || RS_EXIT=$?
RS_END=$(date +%s%N)
RS_EXIT=${RS_EXIT:-0}
RS_TIME_MS=$(( (RS_END - RS_START) / 1000000 ))
echo "  Exit: $RS_EXIT | Time: ${RS_TIME_MS}ms"

# Compare exit codes
echo
if [ "$PY_EXIT" = "$RS_EXIT" ]; then
    echo "✓ Exit codes match: $PY_EXIT"
else
    echo "✗ Exit code mismatch: Python=$PY_EXIT, Rust=$RS_EXIT"
fi

# Speedup
if [ "$PY_TIME_MS" -gt 0 ]; then
    SPEEDUP=$(echo "scale=1; $PY_TIME_MS / $RS_TIME_MS" | bc 2>/dev/null || echo "N/A")
    echo "⚡ Speedup: ${SPEEDUP}×"
fi

# Output diff
echo
echo "─── OUTPUT DIFF ───"
DIFF=$(diff <(echo "$PY_OUTPUT") <(echo "$RS_OUTPUT") 2>&1) || true
if [ -z "$DIFF" ]; then
    echo "✓ Output identical"
else
    echo "$DIFF" | head -30
fi

# Save detailed report
REPORT_FILE="$REPORT_DIR/${LABEL}_${TIMESTAMP}.json"
cat > "$REPORT_FILE" << EOF
{
  "command": "azlin $CMD",
  "timestamp": "$TIMESTAMP",
  "python": {
    "exit_code": $PY_EXIT,
    "time_ms": $PY_TIME_MS,
    "output_lines": $(echo "$PY_OUTPUT" | wc -l)
  },
  "rust": {
    "exit_code": $RS_EXIT,
    "time_ms": $RS_TIME_MS,
    "output_lines": $(echo "$RS_OUTPUT" | wc -l)
  },
  "parity": {
    "exit_codes_match": $([ "$PY_EXIT" = "$RS_EXIT" ] && echo "true" || echo "false"),
    "output_identical": $([ -z "$DIFF" ] && echo "true" || echo "false")
  }
}
EOF
echo
echo "Report saved: $REPORT_FILE"
