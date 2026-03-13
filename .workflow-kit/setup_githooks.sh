#!/usr/bin/env bash
# Managed by AgentWorkflowKit
# Workflow-Version: 1.0.16
# Do not edit in this repository.
# Source profile/file id: .workflow-kit/setup_githooks.sh

__workflow_guard_root="$(git rev-parse --show-toplevel 2>/dev/null || { cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd; })"
if [[ "${WORKFLOW_GUARD_ACTIVE:-0}" != "1" ]]; then
  exec "$__workflow_guard_root/.workflow-kit/workflow_guard.sh" "$0" "$@"
fi
unset __workflow_guard_root

set -euo pipefail

ROOT="$(git rev-parse --show-toplevel)"
"$ROOT/.workflow-kit/assert_workspace.sh"
cd "$ROOT"

HOOKS_DIR="$ROOT/.githooks"
REQUIRED_HOOKS=("commit-msg" "pre-commit" "post-checkout" "post-commit" "pre-push")

if [[ ! -d "$HOOKS_DIR" ]]; then
  echo "Hooks directory not found: $HOOKS_DIR" >&2
  exit 1
fi

for hook in "${REQUIRED_HOOKS[@]}"; do
  hook_file="$HOOKS_DIR/$hook"
  if [[ ! -f "$hook_file" ]]; then
    echo "Required hook file missing: $hook_file" >&2
    exit 1
  fi
  chmod +x "$hook_file"
done

git config core.hooksPath .githooks
configured="$(git config --get core.hooksPath || true)"
if [[ "$configured" != ".githooks" ]]; then
  echo "Failed to configure core.hooksPath=.githooks (current: ${configured:-<empty>})" >&2
  exit 1
fi

echo "[setup-githooks] core.hooksPath=${configured}"
for hook in "${REQUIRED_HOOKS[@]}"; do
  echo "[setup-githooks] ready: .githooks/$hook"
done
echo "[setup-githooks] Hooks are enabled."
