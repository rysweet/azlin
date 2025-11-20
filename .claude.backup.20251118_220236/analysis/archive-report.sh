#!/usr/bin/env bash
# Archive an analysis report to the archive directory
# Usage: ./archive-report.sh <report-file>

set -euo pipefail

if [ $# -eq 0 ]; then
    echo "Usage: $0 <report-file>"
    echo "Example: $0 SECURITY-2025-10-19-xpia-check.md"
    exit 1
fi

REPORT_FILE="$1"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ANALYSIS_DIR="$(dirname "$SCRIPT_DIR")"
ARCHIVE_DIR="$SCRIPT_DIR"

# Verify report exists
if [ ! -f "$ANALYSIS_DIR/$REPORT_FILE" ]; then
    echo "Error: Report not found: $ANALYSIS_DIR/$REPORT_FILE"
    exit 1
fi

# Extract date from filename (assumes YYYY-MM-DD format)
if [[ $REPORT_FILE =~ ([0-9]{4}-[0-9]{2})-[0-9]{2} ]]; then
    YEAR_MONTH="${BASH_REMATCH[1]}"
else
    # Default to current year-month
    YEAR_MONTH="$(date +%Y-%m)"
fi

# Create archive directory if needed
DEST_DIR="$ARCHIVE_DIR/$YEAR_MONTH"
mkdir -p "$DEST_DIR"

# Move report
mv "$ANALYSIS_DIR/$REPORT_FILE" "$DEST_DIR/"
echo "Archived: $REPORT_FILE -> archive/$YEAR_MONTH/"

# Remind to update INDEX.md
echo ""
echo "Remember to update archive/INDEX.md with an entry for this report."
