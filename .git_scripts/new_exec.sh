#!/usr/bin/env bash
# Managed by AgentWorkflowKit
# Workflow-Version: 1.0.2
# Do not edit in this repository.
# Source profile/file id: .git_scripts/new_exec.sh

__workflow_guard_root="$(git rev-parse --show-toplevel 2>/dev/null || { cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd; })"
if [[ "${WORKFLOW_GUARD_ACTIVE:-0}" != "1" ]]; then
  exec "$__workflow_guard_root/.git_scripts/workflow_guard.sh" "$0" "$@"
fi
unset __workflow_guard_root

set -euo pipefail

usage() {
  cat <<'USAGE'
Usage:
  ./.git_scripts/new_exec.sh [--no-sync]

Options:
  --no-sync   Skip default session sync (internal/special flows only)
  -h, --help  Show help
USAGE
}

RUN_SYNC=1
while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --no-sync)
      RUN_SYNC=0
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

ROOT=$(git rev-parse --show-toplevel)
ASSERT_PURPOSE=code "$ROOT/.git_scripts/assert_workspace.sh"
INDEX_FILE="$ROOT/docs/exec_records/INDEX.md"
TARGET_BRANCH="$("$ROOT/.git_scripts/git_default_branch.sh" "$ROOT")"

if [[ ! -f "$INDEX_FILE" ]]; then
  echo "INDEX.md not found at $INDEX_FILE" >&2
  exit 1
fi

if [[ -x "$ROOT/scripts/python_bin.sh" ]]; then
  PYTHON_BIN="${PYTHON_BIN:-$("$ROOT/scripts/python_bin.sh")}"
else
  PYTHON_BIN="${PYTHON_BIN:-$(command -v python3)}"
fi

branch="$(git branch --show-current)"
if [[ "$branch" == "$TARGET_BRANCH" ]]; then
  echo "new_exec must run on a task branch, not $branch." >&2
  echo "Create one first: ./.git_scripts/new_branch.sh \"issue words\"" >&2
  exit 1
fi

if [[ "$RUN_SYNC" -eq 1 ]]; then
  echo "[new-exec] Syncing current branch to latest origin/${TARGET_BRANCH} ..."
  "$ROOT/.git_scripts/session_sync.sh" "$TARGET_BRANCH"
fi

hygiene_json="$("$ROOT/.git_scripts/exec_record_hygiene.py" --target-branch "$TARGET_BRANCH" --apply --reuse-latest)"
reusable_exec_id="$(
  HYGIENE_JSON="$hygiene_json" "$PYTHON_BIN" - <<'PY'
from __future__ import annotations

import json
import os

payload = json.loads(os.environ["HYGIENE_JSON"])
value = payload.get("reusable_exec_id")
print("" if value is None else str(value))
PY
)"
if [[ -n "$reusable_exec_id" ]]; then
  record_file="$ROOT/docs/exec_records/${reusable_exec_id}.md"
  commit_template_file="$ROOT/docs/exec_records/${reusable_exec_id}_commit.txt"
  echo "[new-exec] Reusing existing execution placeholder: $reusable_exec_id"
  echo "Execution ID: $reusable_exec_id"
  echo "Execution record path: $record_file"
  echo "Commit template path: $commit_template_file"
  exit 0
fi

COMMON_GIT_DIR="$(git rev-parse --path-format=absolute --git-common-dir)"
COUNTER_FILE="$COMMON_GIT_DIR/codex_exec_id_next.txt"
LOCK_FILE="$COMMON_GIT_DIR/codex_exec_id.lock"

current_id="$(
  ROOT="$ROOT" INDEX_FILE="$INDEX_FILE" COUNTER_FILE="$COUNTER_FILE" LOCK_FILE="$LOCK_FILE" "$PYTHON_BIN" - <<'PY'
from __future__ import annotations

import fcntl
import os
import re
import subprocess
from pathlib import Path


def _read_int(path: Path) -> int | None:
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _max_id_from_index(path: Path) -> int:
    if not path.exists():
        return 1001
    text = path.read_text(encoding="utf-8")
    max_id = 1000
    for line in text.splitlines():
        line = line.strip()
        match = re.match(r"^\|\s*([0-9]{4,})\s*\|", line)
        if match:
            max_id = max(max_id, int(match.group(1)))
    return max(1001, max_id + 1)


def _max_record_id(records_dir: Path) -> int:
    max_id = 1000
    if not records_dir.exists():
        return max_id
    for item in records_dir.iterdir():
        if not item.is_file():
            continue
        match = re.fullmatch(r"([0-9]{4,})\.md", item.name)
        if match:
            max_id = max(max_id, int(match.group(1)))
    return max_id


def _max_commit_id(repo_root: str) -> int:
    try:
        output = subprocess.check_output(
            ["git", "-C", repo_root, "log", "--all", "--format=%s"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        return 1000

    max_id = 1000
    for line in output.splitlines():
        match = re.match(r"^\[([0-9]{4,})\]\s", line.strip())
        if match:
            max_id = max(max_id, int(match.group(1)))
    return max_id


root = os.environ["ROOT"]
index_file = Path(os.environ["INDEX_FILE"])
counter_file = Path(os.environ["COUNTER_FILE"])
lock_file = Path(os.environ["LOCK_FILE"])
lock_file.parent.mkdir(parents=True, exist_ok=True)

with lock_file.open("a+", encoding="utf-8") as lock:
    fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
    next_from_index = _max_id_from_index(index_file)
    max_record_id = _max_record_id(Path(root) / "docs" / "exec_records")
    max_commit_id = _max_commit_id(root)
    counter_value = _read_int(counter_file)
    seed = max(1001, next_from_index, max_record_id + 1, max_commit_id + 1)
    allocated = seed if counter_value is None or counter_value < seed else counter_value
    counter_file.write_text(f"{allocated + 1}\n", encoding="utf-8")
    print(allocated)
PY
)"

record_file="$ROOT/docs/exec_records/${current_id}.md"
if [[ -f "$record_file" ]]; then
  echo "Execution record already exists in current branch: $record_file" >&2
  echo "If this is intentional, use that ID directly; otherwise rerun ./.git_scripts/new_exec.sh after cleanup." >&2
  exit 1
fi

date_str=$(date +%F)
commit_template_file="$ROOT/docs/exec_records/${current_id}_commit.txt"

cat <<EOF2 > "$record_file"
# ${current_id}

## 完成定义（DoD）

- [ ] 需求目标已明确（含“是否必须 merge 到 ${TARGET_BRANCH} 并删除分支”）
- [ ] 变更验证命令已执行并记录
- [ ] 若为代码任务：已合并到目标分支并完成分支清理

## 需求摘要

TODO

## 变更文件

- TODO

## 变更说明

- TODO

## 验证结果

- TODO

## 完成待办项

- 无

## 当前占用待办项

- 无

## 风险与回滚

- TODO
EOF2

cat <<EOF2 > "$commit_template_file"
[${current_id}] type(scope): summary

# Changes
# - TODO

# Tests
# - TODO

# Risks
# - TODO
EOF2

CURRENT_ID="$current_id" DATE_STR="$date_str" INDEX_FILE="$INDEX_FILE" "$PYTHON_BIN" - <<'PY'
from pathlib import Path
import os
import re

index_path = Path(os.environ["INDEX_FILE"])
current_id = int(os.environ["CURRENT_ID"])
date_str = os.environ["DATE_STR"]

text = index_path.read_text(encoding="utf-8")
lines = text.splitlines()

output = []
existing_row = False
row_pattern = re.compile(rf"^\|\s*{current_id}\s*\|")
new_row = f"| {current_id} | {date_str} | TODO |"
inserted = False

for line in lines:
    stripped = line.strip()
    if row_pattern.match(stripped):
        existing_row = True
    if re.fullmatch(r"`([0-9]{4,})`", stripped):
        continue
    output.append(line)
    if not inserted and line.strip() == "|---|---|---|" and not existing_row:
        output.append(new_row)
        inserted = True

if not inserted and not existing_row:
    output.append(new_row)

index_path.write_text("\n".join(output) + "\n", encoding="utf-8")
PY

if [[ -x "$ROOT/.git_scripts/public_work_register_sync.py" ]]; then
  "$ROOT/.git_scripts/public_work_register_sync.py" >/dev/null
fi

echo "Execution ID: $current_id"
echo "New execution record created: $record_file"
echo "Commit template created: $commit_template_file"
