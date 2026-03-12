#!/usr/bin/env bash
# Managed by AgentWorkflowKit
# Workflow-Version: 1.0.5
# Do not edit in this repository.
# Source profile/file id: .git_scripts/session_release_resume.sh

__workflow_guard_root="$(git rev-parse --show-toplevel 2>/dev/null || { cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd; })"
if [[ "${WORKFLOW_GUARD_ACTIVE:-0}" != "1" ]]; then
  exec "$__workflow_guard_root/.git_scripts/workflow_guard.sh" "$0" "$@"
fi
unset __workflow_guard_root

set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  ./.git_scripts/session_release_resume.sh

Resume a previously failed auto-release after merge conflicts are resolved.
USAGE
}

if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  usage
  exit 0
fi

ROOT="$(git rev-parse --show-toplevel)"
"$ROOT/.git_scripts/assert_workspace.sh"

COMMON_GIT_DIR="$(git rev-parse --path-format=absolute --git-common-dir)"
STATE_FILE="$COMMON_GIT_DIR/codex_release_state.json"
PRIMARY_ROOT="$(dirname "$COMMON_GIT_DIR")"

if [[ ! -f "$STATE_FILE" ]]; then
  echo "[session-release-resume] No pending conflict state file found: $STATE_FILE" >&2
  exit 1
fi

STATE_LINES="$(python3 - "$STATE_FILE" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
data = json.loads(path.read_text(encoding="utf-8"))

def out(key, value):
    value = "" if value is None else str(value)
    print(f"{key}={value}")

out("status", data.get("status", ""))
out("source_branch", data.get("source_branch", ""))
out("target_branch", data.get("target_branch", ""))
out("source_worktree", data.get("source_worktree", ""))
out("merge_base_main_sha", data.get("merge_base_main_sha", ""))
PY
)"

STATUS="$(printf '%s\n' "$STATE_LINES" | awk -F= '$1=="status" {print $2}')"
SOURCE_BRANCH="$(printf '%s\n' "$STATE_LINES" | awk -F= '$1=="source_branch" {print $2}')"
TARGET_BRANCH="$(printf '%s\n' "$STATE_LINES" | awk -F= '$1=="target_branch" {print $2}')"
SOURCE_WORKTREE="$(printf '%s\n' "$STATE_LINES" | awk -F= '$1=="source_worktree" {print $2}')"
MERGE_BASE_MAIN_SHA="$(printf '%s\n' "$STATE_LINES" | awk -F= '$1=="merge_base_main_sha" {print $2}')"

if [[ "$STATUS" != "conflict" ]]; then
  echo "[session-release-resume] State status is not conflict: $STATUS" >&2
  exit 1
fi
if [[ -z "$SOURCE_BRANCH" || -z "$TARGET_BRANCH" || -z "$MERGE_BASE_MAIN_SHA" ]]; then
  echo "[session-release-resume] Invalid release state file: missing required fields." >&2
  exit 1
fi

CURRENT_PRIMARY_BRANCH="$(git -C "$PRIMARY_ROOT" branch --show-current || true)"
if [[ "$CURRENT_PRIMARY_BRANCH" != "$TARGET_BRANCH" ]]; then
  echo "[session-release-resume] Primary repo must be on ${TARGET_BRANCH}, current: ${CURRENT_PRIMARY_BRANCH:-DETACHED}" >&2
  exit 1
fi

PRIMARY_HEAD_SHA="$(git -C "$PRIMARY_ROOT" rev-parse HEAD)"
if [[ "$PRIMARY_HEAD_SHA" != "$MERGE_BASE_MAIN_SHA" ]]; then
  if git -C "$PRIMARY_ROOT" rev-parse --verify --quiet MERGE_HEAD >/dev/null; then
    echo "[session-release-resume] Merge context mismatch: expected base $MERGE_BASE_MAIN_SHA, current $PRIMARY_HEAD_SHA" >&2
    exit 1
  fi
fi

CONFLICT_FILES="$(git -C "$PRIMARY_ROOT" diff --name-only --diff-filter=U || true)"
if [[ -n "$CONFLICT_FILES" ]]; then
  echo "[session-release-resume] Conflicts are still unresolved. Files:" >&2
  while IFS= read -r file; do
    [[ -z "$file" ]] && continue
    echo "  - $file" >&2
  done <<<"$CONFLICT_FILES"
  exit 1
fi

if git -C "$PRIMARY_ROOT" rev-parse --verify --quiet MERGE_HEAD >/dev/null; then
  echo "[session-release-resume] Completing merge commit on ${TARGET_BRANCH} ..."
  git -C "$PRIMARY_ROOT" commit --no-edit --no-verify
else
  if git -C "$PRIMARY_ROOT" show-ref --verify --quiet "refs/heads/${SOURCE_BRANCH}"; then
    if ! git -C "$PRIMARY_ROOT" merge-base --is-ancestor "$SOURCE_BRANCH" "$TARGET_BRANCH"; then
      echo "[session-release-resume] No active merge and source branch is not merged into ${TARGET_BRANCH}." >&2
      exit 1
    fi
  fi
fi

echo "[session-release-resume] Pushing ${TARGET_BRANCH} ..."
git -C "$PRIMARY_ROOT" push --no-verify origin "$TARGET_BRANCH"
git -C "$PRIMARY_ROOT" push --no-verify origin --delete "$SOURCE_BRANCH" || true

if [[ -n "$SOURCE_WORKTREE" && -d "$SOURCE_WORKTREE" ]]; then
  if [[ "$SOURCE_WORKTREE" != "$PRIMARY_ROOT" ]]; then
    git -C "$PRIMARY_ROOT" worktree remove --force "$SOURCE_WORKTREE"
  else
    git -C "$SOURCE_WORKTREE" checkout --detach || true
  fi
fi

git -C "$PRIMARY_ROOT" branch -D "$SOURCE_BRANCH" || true
rm -f "$STATE_FILE"

echo "[session-release-resume] Release cleanup completed."
echo "[session-release-resume] Deleted source branch ${SOURCE_BRANCH}, removed source worktree, and cleared state."
