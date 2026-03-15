#!/usr/bin/env python3
# Managed by AgentWorkflowKit
# Workflow-Version: 1.0.17
# Do not edit in this repository.
# Source profile/file id: .workflow-kit/public_work_register_sync.py
from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if os.environ.get("WORKFLOW_GUARD_ACTIVE") != "1":
    os.execvpe(
        str(REPO_ROOT / ".workflow-kit" / "workflow_guard.sh"),
        [str(REPO_ROOT / ".workflow-kit" / "workflow_guard.sh"), str(Path(__file__).resolve()), *sys.argv[1:]],
        os.environ,
    )

PACKAGE_ROOT = REPO_ROOT / "src" / "main" / "python" / "agent_workflow_kit"
PENDING_WORKLIST_PATH = REPO_ROOT / "docs" / "design" / "pending-worklist.md"
DEFAULT_PENDING_WORKLIST = """# 待处理清单

## 当前清单

| ID | Priority | Decision | Status | 工作项 | 说明 |
|---|---|---|---|---|---|
"""

if str(REPO_ROOT / "src" / "main" / "python") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src" / "main" / "python"))


def ensure_runtime_dirs() -> None:
    (PACKAGE_ROOT / "tooling" / "service").mkdir(parents=True, exist_ok=True)
    PENDING_WORKLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not PENDING_WORKLIST_PATH.exists():
        PENDING_WORKLIST_PATH.write_text(DEFAULT_PENDING_WORKLIST, encoding="utf-8")


def main() -> int:
    ensure_runtime_dirs()
    from agent_workflow_kit.tooling.service.public_work_register_service import PublicWorkRegisterService

    summary = PublicWorkRegisterService().sync_pending_worklist(REPO_ROOT)
    print(
        "[public-work-register] synced pending_count={pending} claim_count={claims} -> {path}".format(
            pending=summary["pending_count"],
            claims=summary["claim_count"],
            path=summary["register_markdown_path"],
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
