#!/usr/bin/env bash
# Managed by AgentWorkflowKit
# Workflow-Version: 1.0.22
# Do not edit in this repository.
# Source profile/file id: .workflow-kit/git_default_branch.sh

__workflow_guard_root="$(git rev-parse --show-toplevel 2>/dev/null || { cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd; })"
if [[ "${WORKFLOW_GUARD_ACTIVE:-0}" != "1" ]]; then
  exec "$__workflow_guard_root/.workflow-kit/workflow_guard.sh" "$0" "$@"
fi
unset __workflow_guard_root

set -euo pipefail

ROOT="${1:-$(git rev-parse --show-toplevel)}"
PREFERRED_BRANCH="main"

branch_exists() {
  local branch_name="$1"
  git -C "$ROOT" show-ref --verify --quiet "refs/heads/${branch_name}" \
    || git -C "$ROOT" show-ref --verify --quiet "refs/remotes/origin/${branch_name}"
}

if branch_exists "$PREFERRED_BRANCH"; then
  echo "$PREFERRED_BRANCH"
  exit 0
fi

if ref="$(git -C "$ROOT" symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null)"; then
  echo "${ref#origin/}"
  exit 0
fi

if branch_exists main; then
  echo "main"
  exit 0
fi

if branch_exists master; then
  echo "master"
  exit 0
fi

echo "$PREFERRED_BRANCH"
