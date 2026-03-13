#!/usr/bin/env bash
# Managed by AgentWorkflowKit
# Workflow-Version: 1.0.8
# Do not edit in this repository.
# Source profile/file id: .git_scripts/ensure_shared_venv.sh

__workflow_guard_root="$(git rev-parse --show-toplevel 2>/dev/null || { cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd; })"
if [[ "${WORKFLOW_GUARD_ACTIVE:-0}" != "1" ]]; then
  exec "$__workflow_guard_root/.git_scripts/workflow_guard.sh" "$0" "$@"
fi
unset __workflow_guard_root

set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  ./.git_scripts/ensure_shared_venv.sh [--target-root <repo-root>] [--replace-existing] [--quiet]

Options:
  --target-root <repo-root>  Repair the target repository/worktree instead of the current one.
  --replace-existing         Back up an existing local virtualenv before relinking it.
  --quiet                    Suppress informational output.
  -h, --help                 Show help.

Environment:
  SHARED_VENV_NAMES          Space-separated candidate names to link.
  SKIP_SHARED_VENV_LINK=1    Skip linking entirely.
USAGE
}

TARGET_ROOT=""
QUIET=0
REPLACE_EXISTING=0
while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --target-root)
      [[ "$#" -ge 2 ]] || {
        echo "Missing value for --target-root" >&2
        exit 1
      }
      TARGET_ROOT="$2"
      shift 2
      ;;
    --replace-existing)
      REPLACE_EXISTING=1
      shift
      ;;
    --quiet)
      QUIET=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ "${SKIP_SHARED_VENV_LINK:-0}" == "1" ]]; then
  exit 0
fi

say() {
  if [[ "$QUIET" -eq 0 ]]; then
    echo "[shared-venv] $*"
  fi
}

backup_existing_target() {
  local repo_root="$1"
  local name="$2"
  local target="$3"
  local backup_root="$repo_root/.cache/workflow-kit/shared-venv-backups"
  local timestamp
  timestamp="$(date +%Y%m%d-%H%M%S)"
  mkdir -p "$backup_root"
  local backup_path="$backup_root/${name#.}-$timestamp"
  mv "$target" "$backup_path"
  say "Moved existing ${name} to ${backup_path}"
}

target_base="${TARGET_ROOT:-$(pwd)}"
ROOT="$(git -C "$target_base" rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "$ROOT" ]]; then
  echo "[shared-venv] Target root is not inside a git repository: $target_base" >&2
  exit 1
fi

COMMON_GIT_DIR="$(git -C "$ROOT" rev-parse --path-format=absolute --git-common-dir)"
PRIMARY_ROOT="$(cd "$COMMON_GIT_DIR/.." && pwd)"
if [[ "$ROOT" == "$PRIMARY_ROOT" ]]; then
  exit 0
fi

venv_name_spec="${SHARED_VENV_NAMES:-.venv314 .venv313 .venv312 .venv311 .venv310 .venv}"
read -r -a VENV_NAMES <<< "$venv_name_spec"

linked_any=0
for name in "${VENV_NAMES[@]}"; do
  source_path="$PRIMARY_ROOT/$name"
  target_path="$ROOT/$name"
  if [[ ! -e "$source_path" && ! -L "$source_path" ]]; then
    continue
  fi

  if [[ -L "$target_path" ]]; then
    if [[ "$(readlink "$target_path")" == "$source_path" ]]; then
      linked_any=1
      continue
    fi
    rm -f "$target_path"
  elif [[ -e "$target_path" ]]; then
    if [[ "$REPLACE_EXISTING" -ne 1 ]]; then
      say "Skip ${name}: ${target_path} already exists. Re-run with --replace-existing to relink."
      continue
    fi
    backup_existing_target "$ROOT" "$name" "$target_path"
  fi

  ln -s "$source_path" "$target_path"
  linked_any=1
  say "Linked ${target_path} -> ${source_path}"
done

if [[ "$linked_any" -eq 0 ]]; then
  say "No shared virtualenv found under ${PRIMARY_ROOT}"
fi
