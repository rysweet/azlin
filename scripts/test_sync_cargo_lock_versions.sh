#!/usr/bin/env bash
# Tests for scripts/sync-cargo-lock-versions.sh.
#
# The case that matters is the one from issue #1100: a workspace member whose
# Cargo.lock entry is a version behind because it was added on a branch that
# predated the last version bump. Branch CI could not see it; main went red.
#
# Usage: ./scripts/test_sync_cargo_lock_versions.sh
# Exit code: 0 = all pass, 1 = a failure

set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT="${REPO_ROOT}/scripts/sync-cargo-lock-versions.sh"
PASS=0
FAIL=0

pass() { PASS=$((PASS + 1)); echo "  ✅ $1"; }
fail() { FAIL=$((FAIL + 1)); echo "  ❌ $1"; }

# Build a throwaway workspace: `version` is the [workspace.package] version,
# and each remaining argument is `name:lock_version[:own]` — `own` marks a
# crate that pins its own version instead of inheriting.
make_workspace() {
  local root version
  root="$(mktemp -d)"
  version="$1"; shift
  mkdir -p "${root}/rust"
  {
    echo '[workspace]'
    echo 'resolver = "2"'
    echo 'members = ['
    for spec in "$@"; do
      echo "    \"crates/${spec%%:*}\","
    done
    echo ']'
    echo ''
    echo '[workspace.package]'
    echo "version = \"${version}\""
  } > "${root}/rust/Cargo.toml"

  {
    echo 'version = 4'
    echo ''
    echo '[[package]]'
    echo 'name = "some-external-crate"'
    echo "version = \"${version}\""
    echo ''
  } > "${root}/rust/Cargo.lock"

  for spec in "$@"; do
    local name lock_version own
    name="${spec%%:*}"
    lock_version="$(echo "${spec}" | cut -d: -f2)"
    own="$(echo "${spec}" | cut -d: -f3)"
    mkdir -p "${root}/rust/crates/${name}"
    {
      echo '[package]'
      echo "name = \"${name}\""
      if [ "${own}" = "own" ]; then
        echo "version = \"${lock_version}\""
      else
        echo 'version.workspace = true'
      fi
    } > "${root}/rust/crates/${name}/Cargo.toml"
    {
      echo '[[package]]'
      echo "name = \"${name}\""
      echo "version = \"${lock_version}\""
      echo ''
    } >> "${root}/rust/Cargo.lock"
  done
  echo "${root}"
}

lock_version_of() {
  grep -A1 -E "^name = \"$2\"\$" "$1/rust/Cargo.lock" \
    | grep -m1 '^version = ' | sed 's/.*"\(.*\)"/\1/'
}

echo "=== sync-cargo-lock-versions.sh ==="
echo ""

# ─── 1. The #1100 scenario ──────────────────────────────────────────────
echo "1. A member left behind by a bump it predates"
root="$(make_workspace 2.6.107 azlin:2.6.106 xtask:2.6.105)"
if ! SYNC_LOCK_REPO_ROOT="${root}" "${SCRIPT}" --check >/dev/null 2>&1; then
  pass "--check fails on the stale lock that broke main"
else
  fail "--check passed on a lock with a member a version behind"
fi
out="$(SYNC_LOCK_REPO_ROOT="${root}" "${SCRIPT}" --check 2>&1)"
if echo "${out}" | grep -q "xtask"; then
  pass "the error names the offending crate"
else
  fail "the error does not name the offending crate: ${out}"
fi
if echo "${out}" | grep -q "cargo update -p xtask"; then
  pass "the error says how to fix it"
else
  fail "the error gives no remedy: ${out}"
fi
if SYNC_LOCK_REPO_ROOT="${root}" "${SCRIPT}" 2.6.107 >/dev/null 2>&1 \
   && [ "$(lock_version_of "${root}" xtask)" = "2.6.107" ] \
   && [ "$(lock_version_of "${root}" azlin)" = "2.6.107" ]; then
  pass "the write mode repairs a member stuck at an older version"
else
  fail "the write mode did not repair the stale member"
fi
rm -rf "${root}"
echo ""

# ─── 2. It does not key off the old version ─────────────────────────────
echo "2. Rewriting does not depend on what the lock currently says"
root="$(make_workspace 3.0.0 azlin:0.0.1 xtask:99.99.99)"
SYNC_LOCK_REPO_ROOT="${root}" "${SCRIPT}" 3.0.0 >/dev/null 2>&1
if [ "$(lock_version_of "${root}" azlin)" = "3.0.0" ] \
   && [ "$(lock_version_of "${root}" xtask)" = "3.0.0" ]; then
  pass "any prior version is overwritten, not just the expected one"
else
  fail "prior versions survived the rewrite"
fi
rm -rf "${root}"
echo ""

# ─── 3. Crates that pin their own version are left alone ────────────────
echo "3. A member with its own version is not clobbered"
root="$(make_workspace 2.6.107 azlin:2.6.107 standalone:1.2.3:own)"
if SYNC_LOCK_REPO_ROOT="${root}" "${SCRIPT}" 2.6.107 >/dev/null 2>&1 \
   && [ "$(lock_version_of "${root}" standalone)" = "1.2.3" ]; then
  pass "an independently-versioned crate keeps its version"
else
  fail "an independently-versioned crate was rewritten"
fi
rm -rf "${root}"
echo ""

# ─── 4. External crates are untouched ───────────────────────────────────
echo "4. Only workspace members are rewritten"
root="$(make_workspace 3.0.0 azlin:1.0.0)"
SYNC_LOCK_REPO_ROOT="${root}" "${SCRIPT}" 3.0.0 >/dev/null 2>&1
if [ "$(lock_version_of "${root}" some-external-crate)" = "3.0.0" ]; then
  # The fixture gives the external crate the workspace version on purpose:
  # a whole-file rewrite would be indistinguishable from a correct one here.
  pass "the external crate that shares the version string is untouched"
else
  fail "an external crate was rewritten"
fi
rm -rf "${root}"
echo ""

# ─── 5. Refuses to disagree with Cargo.toml ─────────────────────────────
echo "5. The version argument cannot contradict Cargo.toml"
root="$(make_workspace 2.6.107 azlin:2.6.107)"
if ! SYNC_LOCK_REPO_ROOT="${root}" "${SCRIPT}" 9.9.9 >/dev/null 2>&1; then
  pass "a version that disagrees with Cargo.toml is rejected"
else
  fail "the script wrote a version Cargo.toml does not declare"
fi
rm -rf "${root}"
echo ""

# ─── 6. A missing lock entry is an error, not a silent pass ─────────────
echo "6. A member absent from the lock fails loudly"
root="$(make_workspace 2.6.107 azlin:2.6.107)"
mkdir -p "${root}/rust/crates/ghost"
printf '[package]\nname = "ghost"\nversion.workspace = true\n' \
  > "${root}/rust/crates/ghost/Cargo.toml"
sed -i 's|^\]$|    "crates/ghost",\n]|' "${root}/rust/Cargo.toml"
if ! SYNC_LOCK_REPO_ROOT="${root}" "${SCRIPT}" --check >/dev/null 2>&1; then
  pass "a member with no lock entry is reported"
else
  fail "a member missing from the lock passed the check"
fi
rm -rf "${root}"
echo ""

# ─── 7. The merged tree, which is what a PR job actually checks ─────────
echo "7. The post-merge shape from #1100"

# On a pull request, actions/checkout checks out the merge commit. Git merges
# the lock as base's entries plus the entry the branch adds — so the tree the
# job sees has the new crate a version behind and everything else current.
# That is the state `--check` has to catch, because it is the state that
# reaches main.
root="$(make_workspace 2.6.106 azlin:2.6.106 azlin-core:2.6.106 xtask:2.6.105)"
out="$(SYNC_LOCK_REPO_ROOT="${root}" "${SCRIPT}" --check 2>&1)"
if [ $? -ne 0 ]; then
  pass "the merged tree that broke main is rejected"
else
  fail "the merged tree that broke main would pass: ${out}"
fi
if echo "${out}" | grep -q "xtask" && ! echo "${out}" | grep -q "error.*azlin-core"; then
  pass "only the stale crate is blamed"
else
  fail "the wrong crates are blamed: ${out}"
fi
rm -rf "${root}"
echo ""

# ─── 8. Manifest layouts the parser must survive ────────────────────────
echo "8. Manifest layouts"

# `members = ["crates/a", "crates/b"]` is valid TOML. Under a line-oriented
# reading the array's range never closed, and every quoted string in the rest
# of the manifest — dependency names, version requirements — became a
# "workspace member".
root="$(mktemp -d)"
mkdir -p "${root}/rust/crates/azlin"
cat > "${root}/rust/Cargo.toml" <<'TOML'
[workspace]
resolver = "2"
members = ["crates/azlin"]

[workspace.package]
version = "1.0.0"

[workspace.dependencies]
serde = "1"
tokio = { version = "1" }
TOML
printf '[package]\nname = "azlin"\nversion.workspace = true\n' \
  > "${root}/rust/crates/azlin/Cargo.toml"
printf 'version = 4\n\n[[package]]\nname = "azlin"\nversion = "1.0.0"\n' \
  > "${root}/rust/Cargo.lock"
out="$(SYNC_LOCK_REPO_ROOT="${root}" "${SCRIPT}" --check 2>&1)"
if [ $? -eq 0 ] && ! echo "${out}" | grep -q "has no Cargo.toml"; then
  pass "an inline members array is parsed correctly"
else
  fail "an inline members array confused the parser: ${out}"
fi
rm -rf "${root}"

# Both spellings of workspace version inheritance have to be recognised, or a
# crate using the table form is silently skipped and its lock entry rots.
root="$(mktemp -d)"
mkdir -p "${root}/rust/crates/azlin"
printf '[workspace]\nmembers = [\n    "crates/azlin",\n]\n\n[workspace.package]\nversion = "2.0.0"\n' \
  > "${root}/rust/Cargo.toml"
printf '[package]\nname = "azlin"\nversion = { workspace = true }\n' \
  > "${root}/rust/crates/azlin/Cargo.toml"
printf 'version = 4\n\n[[package]]\nname = "azlin"\nversion = "1.9.9"\n' \
  > "${root}/rust/Cargo.lock"
out="$(SYNC_LOCK_REPO_ROOT="${root}" "${SCRIPT}" --check 2>&1)"
if echo "${out}" | grep -q "error: rust/Cargo.lock has azlin 1.9.9"; then
  pass "version = { workspace = true } is recognised as inheriting"
else
  fail "the table spelling was treated as an independent version: ${out}"
fi
rm -rf "${root}"

# A members array that never closes must be reported, not silently read to
# end of file.
root="$(mktemp -d)"
mkdir -p "${root}/rust"
printf '[workspace]\nmembers = [\n    "crates/azlin",\n' > "${root}/rust/Cargo.toml"
printf 'version = 4\n' > "${root}/rust/Cargo.lock"
if ! SYNC_LOCK_REPO_ROOT="${root}" "${SCRIPT}" --check >/dev/null 2>&1; then
  pass "an unterminated members array is rejected"
else
  fail "an unterminated members array passed"
fi
rm -rf "${root}"
echo ""

# ─── 9. The real repository is in sync ──────────────────────────────────
echo "9. This repository"
if "${SCRIPT}" --check >/dev/null 2>&1; then
  pass "rust/Cargo.lock matches rust/Cargo.toml"
else
  fail "rust/Cargo.lock is out of sync — run scripts/sync-cargo-lock-versions.sh --check"
fi
echo ""

echo "=== ${PASS} passed, ${FAIL} failed ==="
[ "${FAIL}" -eq 0 ]
