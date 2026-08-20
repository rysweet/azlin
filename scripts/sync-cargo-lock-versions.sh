#!/usr/bin/env bash
# Keep rust/Cargo.lock's workspace-member versions in step with the workspace
# version in rust/Cargo.toml.
#
# Why this exists (issue #1100)
# ----------------------------
# Every crate in this workspace declares `version.workspace = true`, so its
# Cargo.lock entry must equal `[workspace.package] version`. When it does not,
# `cargo build --locked` — which CI uses — refuses to proceed:
#
#     error: cannot update the lock file ... because --locked was passed
#
# That is how main broke on 2026-08-19. The release job had bumped every
# then-known crate to 2.6.106; PR #1099 was authored and CI-verified against a
# 2.6.105 workspace, so its `xtask 2.6.105` lock entry was internally
# consistent and its branch CI was legitimately green. Squash-merging the two
# produced a lock with one member a version behind, and main went red for a
# reason no reviewer could have seen on the branch.
#
# The fix is that this script does not look at what the lock currently says.
# A member that inherits the workspace version has exactly one correct lock
# version, so the old value is irrelevant — matching on it is what made the
# previous implementation both miss the stale entry and, later, fail rather
# than repair it. Members that pin their own version are left alone, and the
# distinction is read from each crate's Cargo.toml rather than assumed.
#
# Usage:
#   scripts/sync-cargo-lock-versions.sh <new-version>   # rewrite and verify
#   scripts/sync-cargo-lock-versions.sh --check         # verify only
#
# On a pull request, `actions/checkout` checks out the *merge* commit, so
# `--check` there is asking the question that matters: does this PR, combined
# with the base branch as it stands, produce a lock cargo will accept? That is
# the question branch CI could not answer in #1100, and it is why this runs as
# its own job rather than only in the release bump.
#
# Exit codes: 0 = lock is (now) in sync, 1 = out of sync or malformed input.

set -euo pipefail

REPO_ROOT="${SYNC_LOCK_REPO_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
CARGO_TOML="${REPO_ROOT}/rust/Cargo.toml"
CARGO_LOCK="${REPO_ROOT}/rust/Cargo.lock"

die() { echo "error: $*" >&2; exit 1; }

[ -f "${CARGO_TOML}" ] || die "no such file: ${CARGO_TOML}"
[ -f "${CARGO_LOCK}" ] || die "no such file: ${CARGO_LOCK}"

MODE="write"
case "${1:-}" in
  --check) MODE="check"; NEW_VERSION="" ;;
  "")      die "usage: $0 <new-version> | --check" ;;
  *)       NEW_VERSION="$1" ;;
esac

# The workspace version declared by a Cargo.toml, or the empty string.
workspace_version_of() {
  sed -n '/^\[workspace\.package\]/,/^\[/p' "$1" \
    | grep -m1 '^version = ' | sed 's/.*"\(.*\)"/\1/' || true
}

# The version a Cargo.lock records for one package, or the empty string when
# the package is not in that lock at all.
#
# The trailing `|| true` matters: without it, `set -e -o pipefail` turns a
# missing package into a mid-loop abort with exit 1 — silent, and
# indistinguishable from a detected problem.
lock_version_of() {
  grep -A1 -E "^name = \"$2\"\$" "$1" 2>/dev/null \
    | grep -m1 '^version = ' | sed 's/.*"\(.*\)"/\1/' || true
}

# The workspace version is the single source of truth for every inheriting
# member.
WORKSPACE_VERSION=$(workspace_version_of "${CARGO_TOML}")
[ -n "${WORKSPACE_VERSION}" ] \
  || die "could not read [workspace.package] version from ${CARGO_TOML}"

if [ "${MODE}" = "check" ]; then
  NEW_VERSION="${WORKSPACE_VERSION}"
elif [ "${NEW_VERSION}" != "${WORKSPACE_VERSION}" ]; then
  die "rust/Cargo.toml says ${WORKSPACE_VERSION} but this script was asked to write ${NEW_VERSION}. Bump Cargo.toml first, so the lock is written from the file that decides the version rather than from an argument."
fi

# Members come from the `members = [...]` array, so adding, renaming or
# removing a crate cannot silently drop it from this loop.
MEMBER_PATHS=$(sed -n '/^members = \[/,/^\]/p' "${CARGO_TOML}" \
  | grep -oE '"[^"]+"' | tr -d '"')
[ -n "${MEMBER_PATHS}" ] \
  || die "could not parse any workspace members from ${CARGO_TOML}"

failures=0
checked=0
for member_path in ${MEMBER_PATHS}; do
  member_toml="${REPO_ROOT}/rust/${member_path}/Cargo.toml"
  [ -f "${member_toml}" ] \
    || die "workspace member '${member_path}' has no Cargo.toml at ${member_toml}"

  pkg=$(sed -n '/^\[package\]/,/^\[/p' "${member_toml}" \
    | grep -m1 '^name = ' | sed 's/.*"\(.*\)"/\1/')
  [ -n "${pkg}" ] || die "could not read package name from ${member_toml}"

  # Only members that inherit the workspace version are ours to rewrite. A
  # crate that pins its own version has a different correct answer, and
  # rewriting it would be the same class of mistake in the other direction.
  if ! grep -qE '^version(\.workspace| *= *\{ *workspace) *= *(true|true *\})' "${member_toml}"; then
    echo "skip ${pkg}: pins its own version (no version.workspace = true)"
    continue
  fi
  checked=$((checked + 1))

  # The lock entry is `name = "<pkg>"` followed on the next line by
  # `version = "..."`. The old value is deliberately not matched on.
  if ! grep -qE "^name = \"${pkg}\"\$" "${CARGO_LOCK}"; then
    echo "error: no [[package]] entry for workspace member '${pkg}' in rust/Cargo.lock" >&2
    failures=$((failures + 1))
    continue
  fi

  if [ "${MODE}" = "write" ]; then
    sed -i "/^name = \"${pkg}\"\$/{n;s/^version = \".*\"\$/version = \"${NEW_VERSION}\"/}" \
      "${CARGO_LOCK}"
  fi

  actual=$(lock_version_of "${CARGO_LOCK}" "${pkg}")

  if [ "${actual}" != "${NEW_VERSION}" ]; then
    echo "error: rust/Cargo.lock has ${pkg} ${actual:-<missing>}, but it inherits the workspace version ${NEW_VERSION}. Run \`cargo update -p ${pkg}\` (or scripts/sync-cargo-lock-versions.sh ${NEW_VERSION}) and commit the lock." >&2
    failures=$((failures + 1))
  else
    echo "ok ${pkg} ${actual}"
  fi
done

[ "${checked}" -gt 0 ] \
  || die "no workspace member inherits the workspace version; the parsing in this script has drifted from the manifests"

if [ "${failures}" -gt 0 ]; then
  echo "" >&2
  echo "rust/Cargo.lock is out of sync with rust/Cargo.toml for ${failures} workspace member(s)." >&2
  echo "\`cargo build --locked\` — which CI uses — will refuse to build this tree." >&2
  exit 1
fi

echo "rust/Cargo.lock is in sync with the workspace version ${NEW_VERSION} (${checked} member(s))."
