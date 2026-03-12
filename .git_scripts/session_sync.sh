#!/usr/bin/env bash
# Managed by AgentWorkflowKit
# Workflow-Version: 1.0.2
# Do not edit in this repository.
# Source profile/file id: .git_scripts/session_sync.sh

__workflow_guard_root="$(git rev-parse --show-toplevel 2>/dev/null || { cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd; })"
if [[ "${WORKFLOW_GUARD_ACTIVE:-0}" != "1" ]]; then
  exec "$__workflow_guard_root/.git_scripts/workflow_guard.sh" "$0" "$@"
fi
unset __workflow_guard_root

set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  ./.git_scripts/session_sync.sh [--dry-run] [target_branch]

Examples:
  ./.git_scripts/session_sync.sh
  ./.git_scripts/session_sync.sh --dry-run
  ./.git_scripts/session_sync.sh <default-branch>
USAGE
}

DRY_RUN=0
ROOT="$(git rev-parse --show-toplevel)"
TARGET_BRANCH="$("$ROOT/.git_scripts/git_default_branch.sh" "$ROOT")"

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      TARGET_BRANCH="$1"
      shift
      ;;
  esac
done
ASSERT_PURPOSE=code "$ROOT/.git_scripts/assert_workspace.sh"
cd "$ROOT"

CURRENT_BRANCH="$(git branch --show-current)"
if [[ -z "$CURRENT_BRANCH" ]]; then
  echo "[session-sync] Unable to detect current branch." >&2
  exit 1
fi
if [[ "$CURRENT_BRANCH" == "$TARGET_BRANCH" ]]; then
  echo "[session-sync] Current branch is target branch (${TARGET_BRANCH}); use a codex/* work branch instead." >&2
  exit 1
fi

if [[ -n "$(git status --porcelain)" ]]; then
  echo "[session-sync] Working tree is not clean. Commit/stash before syncing latest ${TARGET_BRANCH}." >&2
  exit 1
fi

if [[ "$DRY_RUN" -eq 1 ]]; then
  echo "[session-sync] dry-run: git fetch origin ${TARGET_BRANCH}"
  echo "[session-sync] dry-run: rebase current branch onto origin/${TARGET_BRANCH} when needed"
  exit 0
fi

git fetch origin "$TARGET_BRANCH"

if git merge-base --is-ancestor "origin/${TARGET_BRANCH}" "$CURRENT_BRANCH"; then
  echo "[session-sync] Already up to date with origin/${TARGET_BRANCH}."
  exit 0
fi

echo "[session-sync] Rebasing ${CURRENT_BRANCH} onto origin/${TARGET_BRANCH} ..."
git rebase "origin/${TARGET_BRANCH}"
echo "[session-sync] Synced to latest origin/${TARGET_BRANCH}."
