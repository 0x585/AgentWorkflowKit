from __future__ import annotations

import os
import tempfile
import textwrap
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_workflow_kit.tooling.service.public_work_register_service import PublicWorkRegisterService


class PublicWorkRegisterServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.repo_root = Path(self.temp_dir.name) / "AgentWorkflowKit"
        (self.repo_root / "docs" / "design").mkdir(parents=True)
        (self.repo_root / "docs" / "design" / "pending-worklist.md").write_text(
            textwrap.dedent(
                """
                # 待处理清单

                ## 当前清单

                | ID | Priority | Decision | Status | 工作项 | 说明 |
                |---|---|---|---|---|---|
                | W100 | P0 | EXECUTE | IN_PROGRESS | 顶部任务 | 最新项 |
                | W101 | P1 | EXECUTE | PENDING | 次级任务 | 备用 |
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )
        self.register_root = Path(self.temp_dir.name) / "PublicWorkRegister"
        os.environ[PublicWorkRegisterService.ENV_KEY] = str(self.register_root)
        self.addCleanup(lambda: os.environ.pop(PublicWorkRegisterService.ENV_KEY, None))
        self.service = PublicWorkRegisterService()

    def test_sync_writes_shared_register_files(self) -> None:
        summary = self.service.sync_pending_worklist(self.repo_root)
        self.assertEqual(summary["pending_count"], 2)
        markdown_text = (self.register_root / "pending-work-register.md").read_text(encoding="utf-8")
        self.assertIn("| W100 | P0 | EXECUTE | IN_PROGRESS | 顶部任务 | FREE |", markdown_text)

    def test_claim_and_recommend_skip_locked_item(self) -> None:
        claimed = self.service.claim_work_item(self.repo_root, work_id="W100", worker_id="worker-A")
        recommended = self.service.recommend_work_item(self.repo_root)
        self.assertEqual(claimed["claimed_work_id"], "W100")
        self.assertEqual(recommended["recommended_work_id"], "W101")
        self.assertEqual(recommended["skipped_claimed_work_ids"], ["W100"])

    def test_resolve_register_root_reuses_primary_project_name_for_worktrees(self) -> None:
        os.environ.pop(PublicWorkRegisterService.ENV_KEY, None)
        shared_root = Path(self.temp_dir.name) / "shared-register-root"
        worktree_repo_root = Path(self.temp_dir.name) / "AgentWorkflowKit-wt-lock-fix"
        with patch.object(PublicWorkRegisterService, "DEFAULT_REGISTER_ROOT", shared_root):
            with patch.object(
                self.service,
                "_resolve_git_common_dir",
                return_value=Path(self.temp_dir.name) / "AgentWorkflowKit" / ".git",
            ):
                register_root = self.service._resolve_register_root(worktree_repo_root)
        self.assertEqual(register_root, (shared_root / "AgentWorkflowKit").resolve())


if __name__ == "__main__":
    unittest.main()
