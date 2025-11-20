# Analysis Report Archive

Historical analysis reports organized by date.

## Purpose

This archive preserves completed analysis reports for:
- Historical context
- Pattern identification
- Audit trails
- Learning from past issues

## Organization

Reports are organized by year-month:
```
archive/
  2025-10/
  2025-11/
  ...
```

## Archive Process

When archiving a report:
1. Create month directory if needed: `YYYY-MM/`
2. Move report with original filename
3. Add entry below with summary
4. Remove from active analysis directory

## Archived Reports

### 2025-10

None yet - archive created October 19, 2025.

## Retrieval

To find archived reports:
```bash
# Search by keyword
grep -r "keyword" .claude/analysis/archive/

# List by date
ls -la .claude/analysis/archive/2025-10/

# View specific report
cat .claude/analysis/archive/2025-10/SECURITY-2025-10-15-example.md
```

## Retention

- Keep all reports (no automatic deletion)
- Archive is excluded from git (see `.gitignore`)
- Manual cleanup only if disk space critical
