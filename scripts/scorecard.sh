#!/bin/bash
# Master Scorecard Generator
# Tests all commands in both Python and Rust versions

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

PYTHON_BIN="uv run azlin"
RUST_BIN="./rust/target/debug/azlin"
SCENARIOS_DIR="tests/agentic-scenarios"

# Check if a command has an agentic test
has_agentic_test() {
    local cmd="$1"
    # Search for any word from the command in scenario files
    local first_word
    first_word=$(echo "$cmd" | awk '{print $1}')
    if grep -rlq "$first_word" "$SCENARIOS_DIR"/*.yaml 2>/dev/null; then
        return 0
    fi
    return 1
}

# Test a command and return "exit_code time_ms"
test_command() {
    local bin="$1"
    shift
    local start end ms exit_code
    start=$(date +%s%N)
    $bin "$@" --help >/dev/null 2>&1
    exit_code=$?
    end=$(date +%s%N)
    ms=$(( (end - start) / 1000000 ))
    echo "$exit_code $ms"
}

# Header
echo "# Azlin Feature Scorecard"
echo ""
echo "Generated: $(date -u '+%Y-%m-%d %H:%M:%S UTC')"
echo ""
echo "| Feature | Agentic Test | Python Works | Rust Works | Python (ms) | Rust (ms) | Speedup |"
echo "|---------|:---:|:---:|:---:|---:|---:|---:|"

# List of ALL commands to test
COMMANDS=(
    "list"
    "new"
    "start"
    "stop"
    "connect"
    "status"
    "health"
    "cost"
    "ask"
    "do"
    "clone"
    "cp"
    "sync"
    "sync-keys"
    "code"
    "logs"
    "top"
    "kill"
    "killall"
    "destroy"
    "update"
    "os-update"
    "restore"
    "ps"
    "w"
    "session"
    "env set"
    "env list"
    "env delete"
    "env export"
    "env import"
    "env clear"
    "config show"
    "config set"
    "config get"
    "snapshot create"
    "snapshot list"
    "snapshot restore"
    "snapshot delete"
    "storage create"
    "storage list"
    "storage status"
    "storage mount"
    "storage unmount"
    "storage delete"
    "keys rotate"
    "keys list"
    "keys export"
    "keys backup"
    "auth setup"
    "auth test"
    "auth list"
    "auth show"
    "auth remove"
    "tag add"
    "tag remove"
    "tag list"
    "batch stop"
    "batch start"
    "batch command"
    "fleet run"
    "fleet workflow"
    "compose up"
    "compose down"
    "compose ps"
    "template create"
    "template list"
    "template delete"
    "template save"
    "template show"
    "template apply"
    "autopilot enable"
    "autopilot disable"
    "autopilot status"
    "context list"
    "context current"
    "context use"
    "context create"
    "context delete"
    "context rename"
    "disk add"
    "ip check"
    "web start"
    "web stop"
    "costs dashboard"
    "costs history"
    "costs budget"
    "costs recommend"
    "costs actions"
    "github-runner enable"
    "github-runner disable"
    "github-runner status"
    "github-runner scale"
    "doit deploy"
    "sessions save"
    "sessions list"
    "sessions load"
    "sessions delete"
    "bastion list"
    "bastion status"
    "bastion configure"
    "completions bash"
)

# Counters for summary
total=0
py_pass=0
rs_pass=0
agentic_count=0

for cmd in "${COMMANDS[@]}"; do
    # Split cmd into args array
    IFS=' ' read -ra args <<< "$cmd"

    # Test Python
    py_result=$(test_command $PYTHON_BIN "${args[@]}")
    py_exit=$(echo "$py_result" | cut -d' ' -f1)
    py_ms=$(echo "$py_result" | cut -d' ' -f2)

    # Test Rust
    rs_result=$(test_command $RUST_BIN "${args[@]}")
    rs_exit=$(echo "$rs_result" | cut -d' ' -f1)
    rs_ms=$(echo "$rs_result" | cut -d' ' -f2)

    # Check agentic test
    if has_agentic_test "$cmd"; then
        agentic="✅"
        agentic_count=$((agentic_count + 1))
    else
        agentic="⬜"
    fi

    # Status
    if [ "$py_exit" = "0" ]; then
        py_status="✅"
        py_pass=$((py_pass + 1))
    else
        py_status="❌"
    fi

    if [ "$rs_exit" = "0" ]; then
        rs_status="✅"
        rs_pass=$((rs_pass + 1))
    else
        rs_status="❌"
    fi

    # Speedup calculation
    if [ "$py_ms" -gt 0 ] && [ "$rs_ms" -gt 0 ]; then
        speedup=$(echo "scale=0; $py_ms / $rs_ms" | bc 2>/dev/null || echo "?")
        speedup="${speedup}x"
    else
        speedup="N/A"
    fi

    total=$((total + 1))

    echo "| \`$cmd\` | $agentic | $py_status | $rs_status | $py_ms | $rs_ms | $speedup |"
done

# Summary
echo ""
echo "## Summary"
echo ""
echo "- **Total commands tested**: $total"
echo "- **Python passing**: $py_pass / $total"
echo "- **Rust passing**: $rs_pass / $total"
echo "- **With agentic tests**: $agentic_count / $total"
