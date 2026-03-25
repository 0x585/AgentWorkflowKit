#!/usr/bin/env bash
# Managed by AgentWorkflowKit
# Workflow-Version: 1.0.30
# Do not edit in this repository.
# Source profile/file id: .workflow-kit/assert_workspace.sh

__workflow_guard_root="$(git rev-parse --show-toplevel 2>/dev/null || { cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd; })"
if [[ "${WORKFLOW_GUARD_ACTIVE:-0}" != "1" ]]; then
  exec "$__workflow_guard_root/.workflow-kit/workflow_guard.sh" "$0" "$@"
fi
unset __workflow_guard_root

set -euo pipefail

EXPECTED_ROOT="${EXPECTED_WORKSPACE_ROOT:-/Users/pi/PyCharmProject/AgentWorkflowKit}"
ALLOW_GIT_WORKTREE="${ALLOW_GIT_WORKTREE:-1}"
ASSERT_PURPOSE="${ASSERT_PURPOSE:-default}"
EXPECTED_BASE="$(basename "$EXPECTED_ROOT")"
REQUIRED_HOOKS=("commit-msg" "pre-commit" "post-checkout" "post-commit" "pre-push")

classify_worktree_kind() {
  local wt_path="$1"
  local wt_base
  wt_base="$(basename "$wt_path")"
  if [[ "$wt_path" == "$EXPECTED_ROOT" ]]; then
    echo "primary"
    return
  fi
  if [[ "$wt_base" == "$EXPECTED_BASE"-wt-* ]]; then
    echo "managed-worktree"
    return
  fi
  if [[ "$wt_path" == */.codex/worktrees/*/"$EXPECTED_BASE" ]]; then
    echo "codex-worktree"
    return
  fi
  echo "external-worktree"
}

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "$ROOT" ]]; then
  echo "[workspace-check] Not inside a git repository." >&2
  exit 1
fi

DEFAULT_BRANCH="$("$ROOT/.workflow-kit/git_default_branch.sh" "$EXPECTED_ROOT" 2>/dev/null || echo main)"

COMMON_GIT_DIR="$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null || true)"
EXPECTED_COMMON_GIT_DIR="${EXPECTED_ROOT}/.git"
ROOT_KIND="$(classify_worktree_kind "$ROOT")"
MODE="worktree"
if [[ "$ROOT_KIND" == "primary" ]]; then
  MODE="primary"
fi

if [[ "$ASSERT_PURPOSE" != "default" && "$ASSERT_PURPOSE" != "code" ]]; then
  echo "[workspace-check] Invalid ASSERT_PURPOSE: $ASSERT_PURPOSE (allowed: default|code)" >&2
  exit 1
fi

if [[ ! -d "$EXPECTED_ROOT/.git" ]]; then
  echo "[workspace-check] Expected repository not found: $EXPECTED_ROOT" >&2
  exit 1
fi

validate_hooks_configuration() {
  local configured_hooks_path=""
  local hooks_dir=""
  local errors=()
  local err=""
  configured_hooks_path="$(git -C "$ROOT" config --get core.hooksPath || true)"

  if [[ -z "$configured_hooks_path" ]]; then
    errors+=("git core.hooksPath is not set.")
  elif [[ "$configured_hooks_path" == ".githooks" ]]; then
    hooks_dir="$ROOT/.githooks"
  elif [[ "$configured_hooks_path" == "$ROOT/.githooks" || "$configured_hooks_path" == "$EXPECTED_ROOT/.githooks" ]]; then
    hooks_dir="$configured_hooks_path"
  else
    errors+=("git core.hooksPath must be .githooks (current: ${configured_hooks_path}).")
    if [[ "$configured_hooks_path" == /* ]]; then
      hooks_dir="$configured_hooks_path"
    fi
  fi

  if [[ -n "$hooks_dir" ]]; then
    if [[ ! -d "$hooks_dir" ]]; then
      errors+=("hooks directory not found: ${hooks_dir}")
    else
      for hook in "${REQUIRED_HOOKS[@]}"; do
        local hook_file="${hooks_dir}/${hook}"
        if [[ ! -f "$hook_file" ]]; then
          errors+=("missing hook file: ${hook_file}")
          continue
        fi
        if [[ ! -x "$hook_file" ]]; then
          errors+=("hook file is not executable: ${hook_file}")
        fi
      done
    fi
  fi

  if [[ "${#errors[@]}" -eq 0 ]]; then
    return
  fi

  if [[ "$ASSERT_PURPOSE" == "code" ]]; then
    echo "[workspace-check] Git hooks are required in code mode." >&2
    for err in "${errors[@]}"; do
      echo "[workspace-check] - ${err}" >&2
    done
    echo "[workspace-check] Fix: ./.workflow-kit/setup_githooks.sh" >&2
    exit 1
  fi

  for err in "${errors[@]}"; do
    echo "[workspace-check] Warning: ${err}" >&2
  done
  echo "[workspace-check] Warning: run ./.workflow-kit/setup_githooks.sh to enable auto-sync and auto-release hooks." >&2
}

if [[ "$ROOT_KIND" != "primary" ]]; then
  if [[ "$ALLOW_GIT_WORKTREE" != "1" ]]; then
    echo "[workspace-check] Wrong workspace root." >&2
    echo "  expected: $EXPECTED_ROOT" >&2
    echo "  actual:   $ROOT" >&2
    exit 1
  fi

  if [[ "$COMMON_GIT_DIR" != "$EXPECTED_COMMON_GIT_DIR" ]]; then
    echo "[workspace-check] Worktree is not attached to expected primary repository." >&2
    echo "  expected git-common-dir: $EXPECTED_COMMON_GIT_DIR" >&2
    echo "  actual git-common-dir:   $COMMON_GIT_DIR" >&2
    exit 1
  fi
fi

if [[ "$ROOT_KIND" == "external-worktree" ]]; then
  echo "[workspace-check] Worktree path is not supported by workspace policy." >&2
  echo "  path: $ROOT" >&2
  echo "  allowed: ${EXPECTED_BASE}-wt-* OR ~/.codex/worktrees/*/${EXPECTED_BASE}" >&2
  exit 1
fi

is_worktree_clean() {
  local wt_path="$1"
  local status
  status="$(git -C "$wt_path" status --porcelain 2>/dev/null || true)"
  [[ -z "$status" ]]
}

cleanup_abnormal_worktrees() {
  local blocked=0
  local wt_path=""
  local wt_branch=""
  local wt_detached=0

  process_entry() {
    if [[ -z "$wt_path" ]]; then
      return
    fi

    local wt_kind
    wt_kind="$(classify_worktree_kind "$wt_path")"
    if [[ "$wt_kind" != "external-worktree" ]]; then
      return
    fi

    local reasons=("unsupported-worktree-path")
    if [[ "$wt_detached" -eq 1 ]]; then
      reasons+=("detached-head")
    fi
    if [[ -z "$wt_branch" || "$wt_branch" != codex/* ]]; then
      reasons+=("non-codex-branch")
    fi

    if [[ "$wt_path" == "$ROOT" ]]; then
      echo "[workspace-check] Current worktree is abnormal and must be fixed first: $wt_path" >&2
      echo "[workspace-check] Reasons: ${reasons[*]}" >&2
      blocked=1
      return
    fi

    if is_worktree_clean "$wt_path"; then
      echo "[workspace-check] Removing abnormal clean worktree: $wt_path (${reasons[*]})"
      if ! git -C "$EXPECTED_ROOT" worktree remove "$wt_path" >/dev/null 2>&1; then
        echo "[workspace-check] Failed to remove abnormal worktree: $wt_path" >&2
        blocked=1
      fi
      return
    fi

    echo "[workspace-check] Dirty abnormal worktree detected: $wt_path" >&2
    echo "[workspace-check] Reasons: ${reasons[*]}" >&2
    echo "[workspace-check] Resolve manually, then rerun workspace check." >&2
    echo "  git -C \"$wt_path\" status --short" >&2
    echo "  # cleanup after backup: git -C \"$EXPECTED_ROOT\" worktree remove \"$wt_path\"" >&2
    blocked=1
  }

  while IFS= read -r line || [[ -n "$line" ]]; do
    if [[ -z "$line" ]]; then
      process_entry
      wt_path=""
      wt_branch=""
      wt_detached=0
      continue
    fi
    case "$line" in
      worktree\ *)
        wt_path="${line#worktree }"
        ;;
      branch\ refs/heads/*)
        wt_branch="${line#branch refs/heads/}"
        ;;
      detached)
        wt_detached=1
        ;;
    esac
  done < <(git -C "$EXPECTED_ROOT" worktree list --porcelain && echo)

  if [[ "$blocked" -eq 1 ]]; then
    exit 1
  fi
}

cleanup_abnormal_worktrees
validate_hooks_configuration

BRANCH="$(git symbolic-ref --short -q HEAD || true)"
if [[ -z "$BRANCH" ]]; then
  if [[ "$ASSERT_PURPOSE" == "code" ]]; then
    echo "[workspace-check] Code mode requires a branch (detached HEAD is not allowed)." >&2
    echo "  git switch -c codex/<name>   # create and switch" >&2
    echo "  git switch codex/<name>      # switch existing branch" >&2
    exit 1
  fi
  if [[ "$ROOT_KIND" == "codex-worktree" || "$ROOT_KIND" == "managed-worktree" ]]; then
    echo "[workspace-check] Warning: worktree is detached in default mode." >&2
    echo "[workspace-check] Hint: before code edits, switch to codex/* branch." >&2
    echo "  git switch -c codex/<name>   # create and switch" >&2
    echo "  git switch codex/<name>      # switch existing branch" >&2
  else
    echo "[workspace-check] Detached HEAD detected, aborting." >&2
    exit 1
  fi
fi

if [[ "$ASSERT_PURPOSE" == "code" ]]; then
  if [[ "$ROOT_KIND" != "managed-worktree" && "$ROOT_KIND" != "codex-worktree" ]]; then
    echo "[workspace-check] Code edits are only allowed in managed/codex worktrees, not current workspace." >&2
    echo "  kind: $ROOT_KIND" >&2
    exit 1
  fi
  if [[ "$BRANCH" != codex/* ]]; then
    echo "[workspace-check] Code mode branch must use codex/* prefix." >&2
    echo "  branch: $BRANCH" >&2
    echo "  hint: git switch -c codex/<name>" >&2
    exit 1
  fi
  if ! "$ROOT/.workflow-kit/branch_name_policy.py" validate --branch "$BRANCH" --context guard; then
    exit 1
  fi
fi

if [[ "$ASSERT_PURPOSE" == "default" && -n "$BRANCH" ]]; then
  if [[ "$ROOT_KIND" != "primary" ]]; then
    if [[ "$BRANCH" == "$DEFAULT_BRANCH" ]]; then
      echo "[workspace-check] Default branch must stay in primary repository only." >&2
      echo "  branch: $BRANCH" >&2
      echo "  default_branch: $DEFAULT_BRANCH" >&2
      echo "  fix: git checkout --detach  # release branch occupancy in this worktree" >&2
      exit 1
    fi
    if [[ "$BRANCH" != codex/* ]]; then
      echo "[workspace-check] Worktree branch must use codex/* or detached HEAD." >&2
      echo "  branch: $BRANCH" >&2
      exit 1
    fi
  fi
fi

DISPLAY_BRANCH="${BRANCH:-DETACHED}"
echo "[workspace-check] OK: $ROOT (branch=$DISPLAY_BRANCH mode=$MODE kind=$ROOT_KIND purpose=$ASSERT_PURPOSE)"
