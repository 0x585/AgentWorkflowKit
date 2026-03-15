#!/usr/bin/env python3
# Managed by AgentWorkflowKit
# Workflow-Version: 1.0.17
# Do not edit in this repository.
# Source profile/file id: .workflow-kit/pending_worklist_autoclean.py
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if os.environ.get("WORKFLOW_GUARD_ACTIVE") != "1":
    os.execvpe(
        str(REPO_ROOT / ".workflow-kit" / "workflow_guard.sh"),
        [str(REPO_ROOT / ".workflow-kit" / "workflow_guard.sh"), str(Path(__file__).resolve()), *sys.argv[1:]],
        os.environ,
    )


class PendingWorklistAutocleanService:
    EXEC_RECORD_PATTERN = re.compile(r"^docs/exec_records/([0-9]{4,})\.md$")
    WORK_ID_PATTERN = re.compile(r"\bW[0-9]{3}\b")
    COMPLETED_SECTION_HEADER = "## 完成待办项"

    def collect_completed_work_ids_from_exec_record(self, text: str) -> list[str]:
        work_ids: list[str] = []
        in_completed_section = False
        for raw_line in text.splitlines():
            line = raw_line.strip()
            if line.startswith("## "):
                in_completed_section = line == self.COMPLETED_SECTION_HEADER
                continue
            if not in_completed_section or not line:
                continue
            work_ids.extend(self.WORK_ID_PATTERN.findall(line))
        return self._dedupe_preserve_order(work_ids)

    def prune_pending_worklist(self, pending_worklist_text: str, completed_work_ids: list[str]) -> str:
        if not completed_work_ids:
            return pending_worklist_text
        completed_set = set(completed_work_ids)
        pruned_lines: list[str] = []
        for line in pending_worklist_text.splitlines():
            stripped = line.strip()
            if stripped.startswith("| W"):
                work_id = stripped.split("|", 2)[1].strip()
                if work_id in completed_set:
                    continue
            pruned_lines.append(line)
        result = "\n".join(pruned_lines)
        if pending_worklist_text.endswith("\n"):
            result += "\n"
        return result

    def sync_from_staged_exec_records(self, repo_root: Path) -> list[str]:
        staged_exec_records = self._list_staged_exec_records(repo_root)
        completed_work_ids: list[str] = []
        for relative_path in staged_exec_records:
            text = self._read_staged_file(repo_root, relative_path)
            completed_work_ids.extend(self.collect_completed_work_ids_from_exec_record(text))
        completed_work_ids = self._dedupe_preserve_order(completed_work_ids)
        if not completed_work_ids:
            return []
        pending_worklist_path = repo_root / "docs" / "design" / "pending-worklist.md"
        original = pending_worklist_path.read_text(encoding="utf-8")
        updated = self.prune_pending_worklist(original, completed_work_ids)
        if updated != original:
            pending_worklist_path.write_text(updated, encoding="utf-8")
            subprocess.run(["git", "-C", str(repo_root), "add", str(pending_worklist_path)], check=True)
        return completed_work_ids

    def _list_staged_exec_records(self, repo_root: Path) -> list[str]:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
            check=True,
            capture_output=True,
            text=True,
        )
        return [line.strip() for line in result.stdout.splitlines() if self.EXEC_RECORD_PATTERN.match(line.strip())]

    def _read_staged_file(self, repo_root: Path, relative_path: str) -> str:
        result = subprocess.run(
            ["git", "-C", str(repo_root), "show", f":{relative_path}"],
            check=True,
            capture_output=True,
            text=True,
        )
        return result.stdout

    def _dedupe_preserve_order(self, values: list[str]) -> list[str]:
        seen: set[str] = set()
        deduped: list[str] = []
        for value in values:
            if value in seen:
                continue
            seen.add(value)
            deduped.append(value)
        return deduped


def main() -> int:
    completed_work_ids = PendingWorklistAutocleanService().sync_from_staged_exec_records(REPO_ROOT)
    if completed_work_ids:
        print(f"[pending-worklist] removed completed items: {', '.join(completed_work_ids)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
