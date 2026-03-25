#!/usr/bin/env bash
# Managed by AgentWorkflowKit
# Workflow-Version: 1.0.30
# Do not edit in this repository.
# Source profile/file id: .workflow-kit/prepare_task_commit.sh

__workflow_guard_root="$(git rev-parse --show-toplevel 2>/dev/null || { cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd; })"
if [[ "${WORKFLOW_GUARD_ACTIVE:-0}" != "1" ]]; then
  exec "$__workflow_guard_root/.workflow-kit/workflow_guard.sh" "$0" "$@"
fi
unset __workflow_guard_root

set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  ./.workflow-kit/prepare_task_commit.sh [--exec-id <id>] [--stage] [--json]

Options:
  --exec-id <id>  Validate a specific execution record instead of auto-discovering the active one.
  --stage         Run git add -A before the final readiness check.
  --json          Emit machine-friendly JSON.
  -h, --help      Show help.
USAGE
}

ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

CHECK_ARGS=()
PREPARE_ARGS=()
JSON_OUTPUT=0

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --exec-id)
      if [[ "$#" -lt 2 ]]; then
        echo "[prepare-task-commit] Missing value for --exec-id" >&2
        exit 1
      fi
      CHECK_ARGS+=("--exec-id" "$2")
      shift 2
      ;;
    --stage)
      PREPARE_ARGS+=("--stage")
      shift
      ;;
    --json)
      JSON_OUTPUT=1
      PREPARE_ARGS+=("--json")
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "[prepare-task-commit] Unknown argument: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ "$JSON_OUTPUT" -eq 1 ]]; then
  check_cmd=("$ROOT/.workflow-kit/check_exec_plan.py")
  if [[ "${#CHECK_ARGS[@]}" -gt 0 ]]; then
    check_cmd+=("${CHECK_ARGS[@]}")
  fi
  check_cmd+=(--json)
  set +e
  plan_json="$("${check_cmd[@]}")"
  plan_exit=$?
  set -e
  if [[ "$plan_exit" -ne 0 ]]; then
    printf '%s\n' "$plan_json"
    exit "$plan_exit"
  fi

  prepare_cmd=("$ROOT/.workflow-kit/prepare_commit.sh")
  if [[ "${#PREPARE_ARGS[@]}" -gt 0 ]]; then
    prepare_cmd+=("${PREPARE_ARGS[@]}")
  fi
  prepare_json="$("${prepare_cmd[@]}")"
  python3 - "$plan_json" "$prepare_json" <<'PY'
import json
import sys

payload = {
    "plan": json.loads(sys.argv[1]),
    "prepare_commit": json.loads(sys.argv[2]),
}
print(json.dumps(payload, ensure_ascii=False, indent=2))
PY
  exit 0
fi

check_cmd=("$ROOT/.workflow-kit/check_exec_plan.py")
if [[ "${#CHECK_ARGS[@]}" -gt 0 ]]; then
  check_cmd+=("${CHECK_ARGS[@]}")
fi
"${check_cmd[@]}"

prepare_cmd=("$ROOT/.workflow-kit/prepare_commit.sh")
if [[ "${#PREPARE_ARGS[@]}" -gt 0 ]]; then
  prepare_cmd+=("${PREPARE_ARGS[@]}")
fi
exec "${prepare_cmd[@]}"
