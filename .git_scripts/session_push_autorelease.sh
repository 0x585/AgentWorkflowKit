#!/usr/bin/env bash
# Managed by AgentWorkflowKit
# Workflow-Version: 1.0.5
# Do not edit in this repository.
# Source profile/file id: .git_scripts/session_push_autorelease.sh

__workflow_guard_root="$(git rev-parse --show-toplevel 2>/dev/null || { cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd; })"
if [[ "${WORKFLOW_GUARD_ACTIVE:-0}" != "1" ]]; then
  exec "$__workflow_guard_root/.git_scripts/workflow_guard.sh" "$0" "$@"
fi
unset __workflow_guard_root

set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  ./.git_scripts/session_push_autorelease.sh [--source-branch <codex/*>] [--target <branch>]

Examples:
  ./.git_scripts/session_push_autorelease.sh
  ./.git_scripts/session_push_autorelease.sh --source-branch codex/my-task --target <default-branch>
USAGE
}

SOURCE_BRANCH=""
TARGET_BRANCH=""

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --source-branch)
      SOURCE_BRANCH="${2:-}"
      if [[ -z "$SOURCE_BRANCH" ]]; then
        echo "[session-push-autorelease] --source-branch requires a value." >&2
        exit 1
      fi
      shift 2
      ;;
    --target)
      TARGET_BRANCH="${2:-}"
      if [[ -z "$TARGET_BRANCH" ]]; then
        echo "[session-push-autorelease] --target requires a value." >&2
        exit 1
      fi
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "[session-push-autorelease] Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

ROOT="$(git rev-parse --show-toplevel)"
if [[ -z "$TARGET_BRANCH" ]]; then
  TARGET_BRANCH="$("$ROOT/.git_scripts/git_default_branch.sh" "$ROOT")"
fi
ASSERT_PURPOSE=code "$ROOT/.git_scripts/assert_workspace.sh"
cd "$ROOT"

CURRENT_BRANCH="$(git branch --show-current)"
if [[ -z "$SOURCE_BRANCH" ]]; then
  SOURCE_BRANCH="$CURRENT_BRANCH"
fi

if [[ "$SOURCE_BRANCH" != codex/* ]]; then
  echo "[session-push-autorelease] Source branch must use codex/*: $SOURCE_BRANCH" >&2
  exit 1
fi
if [[ "$CURRENT_BRANCH" != "$SOURCE_BRANCH" ]]; then
  echo "[session-push-autorelease] Current branch ($CURRENT_BRANCH) must match source branch ($SOURCE_BRANCH)." >&2
  exit 1
fi
if [[ "$SOURCE_BRANCH" == "$TARGET_BRANCH" ]]; then
  echo "[session-push-autorelease] Source and target branches must differ." >&2
  exit 1
fi

if [[ -n "$(git status --porcelain)" ]]; then
  echo "[session-push-autorelease] Working tree is dirty. Commit/stash before auto release." >&2
  exit 1
fi

git fetch origin "$TARGET_BRANCH" >/dev/null
SYNC_INFO="$("$ROOT/.git_scripts/session_sync_status.sh" --porcelain "$TARGET_BRANCH")"
SYNC_STATUS="$(printf '%s\n' "$SYNC_INFO" | awk -F= '$1=="status" {print $2}')"
SYNC_AHEAD="$(printf '%s\n' "$SYNC_INFO" | awk -F= '$1=="ahead" {print $2}')"
SYNC_BEHIND="$(printf '%s\n' "$SYNC_INFO" | awk -F= '$1=="behind" {print $2}')"
if [[ "$SYNC_STATUS" == "behind" || "$SYNC_STATUS" == "diverged" ]]; then
  echo "[session-push-autorelease] Branch sync status is ${SYNC_STATUS} (ahead=${SYNC_AHEAD:-0}, behind=${SYNC_BEHIND:-0}) vs origin/${TARGET_BRANCH}." >&2
  echo "[session-push-autorelease] Run ./.git_scripts/session_sync.sh ${TARGET_BRANCH} before auto release." >&2
  exit 1
fi

COMMON_GIT_DIR="$(git rev-parse --path-format=absolute --git-common-dir)"
PRIMARY_ROOT="$(dirname "$COMMON_GIT_DIR")"
STATE_FILE="$COMMON_GIT_DIR/codex_release_state.json"

if [[ -f "$STATE_FILE" ]]; then
  state_status="$(python3 - "$STATE_FILE" <<'PY'
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
try:
    data = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    print("invalid")
    raise SystemExit(0)
print(str(data.get("status", "")))
PY
)"
  if [[ "$state_status" == "conflict" ]]; then
    echo "[session-push-autorelease] Pending conflict release state exists: $STATE_FILE" >&2
    echo "[session-push-autorelease] Resolve conflict first: ./.git_scripts/session_release_resume.sh" >&2
    exit 1
  fi
fi

if [[ -n "$(git -C "$PRIMARY_ROOT" status --porcelain)" ]]; then
  echo "[session-push-autorelease] Primary repository is dirty: $PRIMARY_ROOT" >&2
  echo "[session-push-autorelease] Clean it before auto release." >&2
  exit 1
fi

cleanup_source_worktree() {
  if [[ "$ROOT" == "$PRIMARY_ROOT" ]]; then
    git -C "$ROOT" checkout --detach || true
    return 0
  fi

  if [[ -d "$ROOT" ]]; then
    git -C "$PRIMARY_ROOT" worktree remove --force "$ROOT"
  fi
}

echo "[session-push-autorelease] Pushing source branch: ${SOURCE_BRANCH}"
git push --no-verify -u origin "$SOURCE_BRANCH"

echo "[session-push-autorelease] Preparing merge in primary repo: ${PRIMARY_ROOT}"
git -C "$PRIMARY_ROOT" checkout "$TARGET_BRANCH"
git -C "$PRIMARY_ROOT" pull --ff-only origin "$TARGET_BRANCH"
MAIN_BASE_SHA="$(git -C "$PRIMARY_ROOT" rev-parse HEAD)"

echo "[session-push-autorelease] Merging ${SOURCE_BRANCH} -> ${TARGET_BRANCH}"
if git -C "$PRIMARY_ROOT" merge --no-ff "$SOURCE_BRANCH"; then
  git -C "$PRIMARY_ROOT" push --no-verify origin "$TARGET_BRANCH"
  git -C "$PRIMARY_ROOT" push --no-verify origin --delete "$SOURCE_BRANCH" || true

  cleanup_source_worktree
  git -C "$PRIMARY_ROOT" branch -D "$SOURCE_BRANCH" || true
  rm -f "$STATE_FILE"

  echo "[session-push-autorelease] Released ${SOURCE_BRANCH} -> ${TARGET_BRANCH}."
  echo "[session-push-autorelease] Deleted local/remote source branch and removed source worktree."
  exit 0
fi

CONFLICT_FILES="$(git -C "$PRIMARY_ROOT" diff --name-only --diff-filter=U || true)"
if [[ -z "$CONFLICT_FILES" ]]; then
  echo "[session-push-autorelease] Merge failed without conflict files. Abort merge for safety." >&2
  git -C "$PRIMARY_ROOT" merge --abort >/dev/null 2>&1 || true
  exit 1
fi

CONFLICT_FILES_PAYLOAD="$CONFLICT_FILES" python3 - "$STATE_FILE" "$SOURCE_BRANCH" "$TARGET_BRANCH" "$ROOT" "$MAIN_BASE_SHA" "$PRIMARY_ROOT" <<'PY'
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

state_file = Path(sys.argv[1])
source_branch = sys.argv[2]
target_branch = sys.argv[3]
source_worktree = sys.argv[4]
merge_base_main_sha = sys.argv[5]
primary_root = sys.argv[6]
conflict_files = [
    line.strip()
    for line in os.environ.get("CONFLICT_FILES_PAYLOAD", "").splitlines()
    if line.strip()
]

payload = {
    "status": "conflict",
    "created_at": datetime.now(timezone.utc).isoformat(),
    "source_branch": source_branch,
    "target_branch": target_branch,
    "source_worktree": source_worktree,
    "primary_root": primary_root,
    "merge_base_main_sha": merge_base_main_sha,
    "conflict_files": conflict_files,
}
state_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

echo "[session-push-autorelease] Merge conflict detected. Conflict context is preserved."
echo "[session-push-autorelease] Conflict files:"
while IFS= read -r file; do
  [[ -z "$file" ]] && continue
  echo "  - $file"
done <<<"$CONFLICT_FILES"
echo "[session-push-autorelease] Resume after resolving conflicts: ./.git_scripts/session_release_resume.sh"
echo "[session-push-autorelease] State file: $STATE_FILE"
exit 1
