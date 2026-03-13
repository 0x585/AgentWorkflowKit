#!/usr/bin/env bash
# Managed by AgentWorkflowKit
# Workflow-Version: 1.0.5
# Do not edit in this repository.
# Source profile/file id: .workflow-kit/workflow_guard.sh

set -euo pipefail

ROOT="$(git rev-parse --show-toplevel 2>/dev/null || { cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd; })"
ENTRY_SCRIPT="${1:-}"
if [[ -z "$ENTRY_SCRIPT" ]]; then
  echo "[workflow-guard] Missing entry script path." >&2
  exit 1
fi
shift || true

if [[ -x "$ROOT/scripts/python_bin.sh" ]]; then
  PYTHON_BIN="${PYTHON_BIN:-$("$ROOT/scripts/python_bin.sh")}"
else
  PYTHON_BIN="${PYTHON_BIN:-$(command -v python3 || true)}"
fi

if [[ -z "${PYTHON_BIN:-}" ]]; then
  echo "[workflow-guard] Python interpreter not found." >&2
  exit 1
fi

SOURCE_JSON="$ROOT/.workflow-kit/source.json"
if [[ ! -f "$SOURCE_JSON" ]]; then
  echo "[workflow-guard] Missing workflow source metadata: $SOURCE_JSON" >&2
  exit 1
fi

WORKFLOW_ROOT="$(
  "$PYTHON_BIN" - "$SOURCE_JSON" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
root = payload.get("workflow_repo_root") or payload.get("source_repo_root")
print("" if root is None else str(root))
PY
)"
if [[ -z "$WORKFLOW_ROOT" || ! -d "$WORKFLOW_ROOT" ]]; then
  echo "[workflow-guard] Invalid workflow source root: ${WORKFLOW_ROOT:-<empty>}" >&2
  exit 1
fi

ENTRY_ABS="$(
  "$PYTHON_BIN" - "$ROOT" "$ENTRY_SCRIPT" <<'PY'
import sys
from pathlib import Path

repo_root = Path(sys.argv[1]).resolve()
entry = Path(sys.argv[2])
print(str(entry if entry.is_absolute() else (repo_root / entry).resolve()))
PY
)"

if [[ "$WORKFLOW_ROOT" == "$ROOT" ]]; then
  exec env WORKFLOW_GUARD_ACTIVE=1 "$ENTRY_ABS" "$@"
fi

CHECK_SCRIPT="$WORKFLOW_ROOT/scripts/check_release.py"
APPLY_SCRIPT="$WORKFLOW_ROOT/scripts/apply_release.py"
if [[ ! -f "$CHECK_SCRIPT" || ! -f "$APPLY_SCRIPT" ]]; then
  echo "[workflow-guard] Missing central release tooling in $WORKFLOW_ROOT" >&2
  exit 1
fi

set +e
env WORKFLOW_GUARD_ACTIVE=1 "$ENTRY_ABS" "$@"
ENTRY_STATUS=$?
set -e

if [[ "$ENTRY_STATUS" -eq 0 ]]; then
  exit 0
fi

set +e
CHECK_OUTPUT="$("$PYTHON_BIN" "$CHECK_SCRIPT" --repo-root "$ROOT" --json 2>&1)"
CHECK_STATUS=$?
set -e

case "$CHECK_STATUS" in
  0)
    exit "$ENTRY_STATUS"
    ;;
  10)
    echo "[workflow-guard] Entry script failed (exit=${ENTRY_STATUS}); installed release is outdated. Applying latest release and retrying..." >&2
    "$PYTHON_BIN" "$APPLY_SCRIPT" --repo-root "$ROOT"
    exec env WORKFLOW_GUARD_ACTIVE=1 "$ENTRY_ABS" "$@"
    ;;
  *)
    printf '%s\n' "$CHECK_OUTPUT" >&2
    echo "[workflow-guard] Entry script failed (exit=${ENTRY_STATUS}) and workflow validation also failed. Fix drift or metadata issues before continuing." >&2
    exit "$CHECK_STATUS"
    ;;
esac
