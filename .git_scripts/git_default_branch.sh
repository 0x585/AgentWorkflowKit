#!/usr/bin/env bash
# Managed by AgentWorkflowKit
# Workflow-Version: 1.0.2
# Do not edit in this repository.
# Source profile/file id: .git_scripts/git_default_branch.sh

__workflow_guard_root="$(git rev-parse --show-toplevel 2>/dev/null || { cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd; })"
if [[ "${WORKFLOW_GUARD_ACTIVE:-0}" != "1" ]]; then
  exec "$__workflow_guard_root/.git_scripts/workflow_guard.sh" "$0" "$@"
fi
unset __workflow_guard_root

set -euo pipefail

ROOT="${1:-$(git rev-parse --show-toplevel)}"

if ref="$(git -C "$ROOT" symbolic-ref --quiet --short refs/remotes/origin/HEAD 2>/dev/null)"; then
  echo "${ref#origin/}"
  exit 0
fi

if git -C "$ROOT" show-ref --verify --quiet refs/heads/main \
  || git -C "$ROOT" show-ref --verify --quiet refs/remotes/origin/main; then
  echo "main"
  exit 0
fi

if git -C "$ROOT" show-ref --verify --quiet refs/heads/master \
  || git -C "$ROOT" show-ref --verify --quiet refs/remotes/origin/master; then
  echo "master"
  exit 0
fi

echo "main"
