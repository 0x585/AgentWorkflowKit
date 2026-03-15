#!/usr/bin/env bash
# Managed by AgentWorkflowKit
# Workflow-Version: 1.0.17
# Do not edit in this repository.
# Source profile/file id: .workflow-kit/new_branch.sh

__workflow_guard_root="$(git rev-parse --show-toplevel 2>/dev/null || { cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd; })"
if [[ "${WORKFLOW_GUARD_ACTIVE:-0}" != "1" ]]; then
  exec "$__workflow_guard_root/.workflow-kit/workflow_guard.sh" "$0" "$@"
fi
unset __workflow_guard_root

set -euo pipefail

ROOT=$(git rev-parse --show-toplevel)
"$ROOT/.workflow-kit/assert_workspace.sh"
cd "$ROOT"

dry_run=0
if [[ "${1:-}" == "--dry-run" ]]; then
  dry_run=1
  shift
fi

input="${*:-}"

if [[ -z "$input" ]]; then
  if [[ ! -t 0 ]]; then
    input="$(cat)"
  else
    read -r -p "Issue words (english): " input
  fi
fi

to_slug_words() {
  local text="$1"
  python3 - "$text" <<'PY'
import re
import sys

text = sys.argv[1].strip()
if not text:
    print("task")
    raise SystemExit(0)

tokens = re.findall(r"[A-Za-z0-9]+", text.lower())
if not tokens:
    print("task")
    raise SystemExit(0)

picked = tokens[:3]
name = "-".join(picked)
if len(name) > 24:
    initials = "".join(t[0] for t in picked if t)
    name = initials or picked[0][:12]

print(name)
PY
}

normalize_name() {
  local text="$1"
  echo "$text" \
    | tr '[:upper:]' '[:lower:]' \
    | sed -E 's/[^a-z0-9]+/-/g; s/^-+//; s/-+$//; s/-{2,}/-/g'
}

branch_name=""
if [[ "$input" == codex/* ]]; then
  suffix="${input#codex/}"
  suffix="$(normalize_name "$suffix")"
  if [[ -z "$suffix" ]]; then
    echo "Invalid branch name: $input" >&2
    exit 1
  fi
  branch_name="codex/$suffix"
elif [[ "$input" =~ ^[A-Za-z0-9._/-]+$ ]]; then
  suffix="$(normalize_name "$input")"
  if [[ -z "$suffix" ]]; then
    echo "Invalid branch name: $input" >&2
    exit 1
  fi
  branch_name="codex/$suffix"
else
  derived="$(to_slug_words "$input")"
  if [[ -z "$derived" ]]; then
    echo "Unable to derive branch name from description: $input" >&2
    exit 1
  fi
  branch_name="codex/$derived"
fi

if [[ "$dry_run" -eq 1 ]]; then
  echo "$branch_name"
  exit 0
fi

if git show-ref --verify --quiet "refs/heads/$branch_name"; then
  git checkout "$branch_name"
  echo "Switched to existing branch: $branch_name"
else
  git checkout -b "$branch_name"
  echo "Created and switched to branch: $branch_name"
fi

if [[ "$branch_name" == codex/* ]]; then
  git config "branch.${branch_name}.remote" origin
  git config "branch.${branch_name}.merge" "refs/heads/${branch_name}"
fi

echo "Next step: ./.workflow-kit/new_exec.sh (or prefer ./.workflow-kit/new_worktree.sh for parallel work)"
