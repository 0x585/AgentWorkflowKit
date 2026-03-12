from __future__ import annotations

import os
import tempfile
import textwrap
import unittest
from pathlib import Path

from agent_workflow_kit.tooling.service.public_work_register_service import PublicWorkRegisterService


class PublicWorkRegisterServiceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.repo_root = Path(self.temp_dir.name) / "repo"
        (self.repo_root / "docs" / "design").mkdir(parents=True)
        self.register_root = Path(self.temp_dir.name) / "PublicWorkRegister"
        os.environ[PublicWorkRegisterService.ENV_KEY] = str(self.register_root)
        self.addCleanup(lambda: os.environ.pop(PublicWorkRegisterService.ENV_KEY, None))
        (self.repo_root / "docs" / "design" / "pending-worklist.md").write_text(
            textwrap.dedent(
                """
                # 待处理清单

                ## 当前清单

                | ID | Priority | Decision | Status | 工作项 | 说明 |
                |---|---|---|---|---|---|
                | W900 | P0 | EXECUTE | IN_PROGRESS | 顶部任务 | 最新会话新增项 |
                | W901 | P0 | EXECUTE | BLOCKED | 阻塞任务 | 暂时跳过 |
                | W902 | P1 | EXECUTE | PENDING | 次级任务 | 备用 |
                """
            ).strip()
            + "\n",
            encoding="utf-8",
        )
        self.service = PublicWorkRegisterService()

    def test_sync_writes_shared_register_files(self) -> None:
        summary = self.service.sync_pending_worklist(self.repo_root)
        self.assertEqual(summary["pending_count"], 3)
        markdown_path = self.register_root / "pending-work-register.md"
        state_path = self.register_root / ".pending-work-register.state.json"
        self.assertTrue(markdown_path.is_file())
        self.assertTrue(state_path.is_file())
        self.assertIn("| W900 | P0 | EXECUTE | IN_PROGRESS | 顶部任务 | FREE |", markdown_path.read_text(encoding="utf-8"))

    def test_claim_and_release_roundtrip(self) -> None:
        claim_summary = self.service.claim_work_item(self.repo_root, worker_id="worker-A", ttl_seconds=300)
        self.assertEqual("W900", claim_summary["claimed_work_id"])
        release_summary = self.service.release_work_item(self.repo_root, work_id="W900", worker_id="worker-A")
        self.assertEqual("RELEASED", release_summary["release_state"])


if __name__ == "__main__":
    unittest.main()
