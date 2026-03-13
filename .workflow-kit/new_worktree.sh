#!/usr/bin/env bash
# Managed by AgentWorkflowKit
# Workflow-Version: 1.0.16
# Do not edit in this repository.
# Source profile/file id: .workflow-kit/new_worktree.sh

__workflow_guard_root="$(git rev-parse --show-toplevel 2>/dev/null || { cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd; })"
if [[ "${WORKFLOW_GUARD_ACTIVE:-0}" != "1" ]]; then
  exec "$__workflow_guard_root/.workflow-kit/workflow_guard.sh" "$0" "$@"
fi
unset __workflow_guard_root

set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
"$ROOT/.workflow-kit/assert_workspace.sh"
cd "$ROOT"
DEFAULT_BRANCH="$("$ROOT/.workflow-kit/git_default_branch.sh" "$ROOT")"

EXPECTED_ROOT="${EXPECTED_WORKSPACE_ROOT:-/Users/pi/PyCharmProject/AgentWorkflowKit}"
if [[ "$ROOT" != "$EXPECTED_ROOT" ]]; then
  echo "Run this script from primary repository root: $EXPECTED_ROOT" >&2
  exit 1
fi

input="${*:-}"
if [[ -z "$input" ]]; then
  if [[ ! -t 0 ]]; then
    input="$(cat)"
  else
    read -r -p "Issue words (english): " input
  fi
fi

branch_name="$("$ROOT/.workflow-kit/new_branch.sh" --dry-run "$input" | tail -n 1 | tr -d '\r')"
if [[ "$branch_name" != codex/* ]]; then
  echo "Failed to derive codex/* branch name from input: $input" >&2
  echo "Derived value: $branch_name" >&2
  exit 1
fi
suffix="${branch_name#codex/}"
base_dir="${WORKTREE_BASE_DIR:-$(dirname "$EXPECTED_ROOT")}"
worktree_path="${base_dir}/$(basename "$EXPECTED_ROOT")-wt-${suffix}"

if [[ -e "$worktree_path" ]]; then
  echo "Worktree path already exists: $worktree_path" >&2
  exit 1
fi

if git show-ref --verify --quiet "refs/heads/${branch_name}"; then
  echo "Branch already exists locally: ${branch_name}" >&2
  echo "Use a different issue word or delete existing branch first." >&2
  exit 1
fi

if ! git ls-remote --exit-code --heads origin "$DEFAULT_BRANCH" >/dev/null 2>&1; then
  echo "Remote branch origin/${DEFAULT_BRANCH} is not available yet." >&2
  echo "Bootstrap the repository default branch before creating managed worktrees." >&2
  exit 1
fi

git fetch origin "$DEFAULT_BRANCH"
git worktree add -b "$branch_name" "$worktree_path" "origin/${DEFAULT_BRANCH}"
git -C "$EXPECTED_ROOT" config "branch.${branch_name}.remote" origin
git -C "$EXPECTED_ROOT" config "branch.${branch_name}.merge" "refs/heads/${branch_name}"
if [[ -x "$ROOT/.workflow-kit/ensure_shared_venv.sh" ]]; then
  "$ROOT/.workflow-kit/ensure_shared_venv.sh" --target-root "$worktree_path" --quiet || \
    echo "[new-worktree] Warning: failed to repair shared virtualenv link for ${worktree_path}" >&2
fi

exec_output="$(cd "$worktree_path" && "$ROOT/.workflow-kit/new_exec.sh")"
exec_id="$(printf '%s\n' "$exec_output" | awk -F': ' '/^Execution ID: / {print $2; exit}')"

echo "Created worktree:"
echo "  branch: ${branch_name}"
echo "  path:   ${worktree_path}"
if [[ -n "$exec_id" ]]; then
  echo "  exec:   ${exec_id}"
fi
echo ""
echo "$exec_output"
