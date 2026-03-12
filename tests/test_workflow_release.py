from __future__ import annotations

import subprocess
import tempfile
import unittest
import shutil
from pathlib import Path

from scripts.workflow_kit_lib import (
    apply_release_to_repo,
    apply_rendered_entries,
    build_lock_manifest,
    check_repo_release,
    export_runtime_templates,
    inject_block,
    load_repo_config,
    prepare_release_artifacts,
    render_repo_entries,
    write_release_artifacts,
    write_json,
)


class WorkflowReleaseTest(unittest.TestCase):
    def setUp(self) -> None:
        self.workflow_root = Path(__file__).resolve().parents[1]
        self.version = "1.0.0"
        self.release_payload, _ = prepare_release_artifacts(
            workflow_root=self.workflow_root,
            profile="full_codex_flow",
            version=self.version,
            repo_ids=["AgentTask", "AgentTransitStation"],
        )
        self.release_hash = str(self.release_payload["release_manifest_hash"])

    def snapshot_files(self, repo_root: Path) -> dict[str, str]:
        return {
            str(path.relative_to(repo_root)): path.read_text(encoding="utf-8")
            for path in sorted(repo_root.rglob("*"))
            if path.is_file()
        }

    def write_repo_docs(self, repo_root: Path) -> None:
        (repo_root / "README.md").write_text("# Temp Repo\n", encoding="utf-8")
        (repo_root / "AGENTS.md").write_text("# Temp Agents\n", encoding="utf-8")

    def copy_runtime_sources(self, target_root: Path) -> None:
        shutil.copytree(self.workflow_root / ".git_scripts", target_root / ".git_scripts")
        shutil.copytree(self.workflow_root / ".githooks", target_root / ".githooks")

    def test_repo_specific_render_differs(self) -> None:
        agent_task = load_repo_config(self.workflow_root, "AgentTask")
        agent_transit = load_repo_config(self.workflow_root, "AgentTransitStation")
        task_entries = render_repo_entries(
            workflow_root=self.workflow_root,
            repo_root=Path(agent_task["expected_workspace_root"]),
            repo_config=agent_task,
            workflow_version=self.version,
            release_hash=self.release_hash,
        )
        transit_entries = render_repo_entries(
            workflow_root=self.workflow_root,
            repo_root=Path(agent_transit["expected_workspace_root"]),
            repo_config=agent_transit,
            workflow_version=self.version,
            release_hash=self.release_hash,
        )
        task_assert = next(entry for entry in task_entries if entry["path"] == ".git_scripts/assert_workspace.sh")
        transit_assert = next(entry for entry in transit_entries if entry["path"] == ".git_scripts/assert_workspace.sh")
        self.assertIn("/Users/pi/PyCharmProject/AgentTask", task_assert["content"])
        self.assertIn("/Users/pi/PyCharmProject/AgentTransitStation", transit_assert["content"])
        self.assertNotEqual(task_assert["sha256"], transit_assert["sha256"])

    def test_apply_rendered_entries_is_idempotent(self) -> None:
        repo_config = load_repo_config(self.workflow_root, "AgentTask").copy()
        with tempfile.TemporaryDirectory() as tmp_dir:
            repo_root = Path(tmp_dir)
            repo_config["repo_id"] = "AgentTask"
            repo_config["expected_workspace_root"] = str(repo_root)
            self.write_repo_docs(repo_root)
            rendered_entries = render_repo_entries(
                workflow_root=self.workflow_root,
                repo_root=repo_root,
                repo_config=repo_config,
                workflow_version=self.version,
                release_hash=self.release_hash,
            )
            apply_rendered_entries(repo_root, rendered_entries)
            first_snapshot = self.snapshot_files(repo_root)
            apply_rendered_entries(repo_root, rendered_entries)
            second_snapshot = self.snapshot_files(repo_root)
            self.assertEqual(first_snapshot, second_snapshot)

    def test_lock_manifest_contains_repo_entries(self) -> None:
        lock_payload = build_lock_manifest(
            workflow_root=self.workflow_root,
            profile="full_codex_flow",
            version=self.version,
            release_hash=self.release_hash,
        )
        self.assertIn("AgentTask", lock_payload["repositories"])
        self.assertIn("AgentTransitStation", lock_payload["repositories"])
        task_paths = {entry["path"] for entry in lock_payload["repositories"]["AgentTask"]["entries"]}
        transit_paths = {entry["path"] for entry in lock_payload["repositories"]["AgentTransitStation"]["entries"]}
        self.assertIn(".git_scripts/new_exec.sh", task_paths)
        self.assertIn(".git_scripts/new_exec.sh", transit_paths)

    def test_inject_block_replaces_managed_region(self) -> None:
        original = "# Header\n\n<!-- workflow-kit:readme:start -->\nold\n<!-- workflow-kit:readme:end -->\n"
        updated = inject_block(
            original=original,
            start_marker="<!-- workflow-kit:readme:start -->",
            end_marker="<!-- workflow-kit:readme:end -->",
            managed_text="new content\n",
        )
        self.assertIn("new content", updated)
        self.assertNotIn("\nold\n", updated)

    def test_apply_release_to_repo_ignores_managed_git_runtime_and_removes_legacy_scripts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            workflow_root = temp_root / "workflow"
            shutil.copytree(self.workflow_root / "profiles", workflow_root / "profiles")
            shutil.copytree(self.workflow_root / "templates", workflow_root / "templates")
            shutil.copytree(self.workflow_root / "repos", workflow_root / "repos")

            repo_root = temp_root / "TempRepo"
            repo_root.mkdir(parents=True)
            subprocess.run(["git", "init", str(repo_root)], check=True, capture_output=True, text=True)
            self.write_repo_docs(repo_root)
            legacy_scripts_dir = repo_root / "scripts"
            legacy_scripts_dir.mkdir(parents=True, exist_ok=True)
            legacy_file = legacy_scripts_dir / "new_branch.sh"
            legacy_file.write_text("# legacy\n", encoding="utf-8")

            repo_config = {
                "repo_id": "TempRepo",
                "profile": "full_codex_flow",
                "expected_workspace_root": str(repo_root),
                "default_branch": "main",
                "python_package_name": "temp_repo",
                "compile_main_path": "src/main/python/temp_repo",
                "compile_test_path": "src/test/python/temp_repo",
                "public_work_register_dir": str(temp_root / "PublicWorkRegister" / "TempRepo"),
            }
            write_json(workflow_root / "repos" / "TempRepo.json", repo_config)
            payload, lock_payload = prepare_release_artifacts(
                workflow_root=workflow_root,
                profile="full_codex_flow",
                version="1.0.0",
                repo_ids=["TempRepo"],
            )
            write_release_artifacts(
                workflow_root=workflow_root,
                profile="full_codex_flow",
                version="1.0.0",
                release_payload=payload,
                lock_payload=lock_payload,
            )

            summary = apply_release_to_repo(
                workflow_root=workflow_root,
                repo_root=repo_root,
                repo_id="TempRepo",
            )

            self.assertEqual("TempRepo", summary["repo_id"])
            self.assertIn(str(legacy_file.resolve()), summary["removed_legacy_paths"])
            self.assertFalse(legacy_file.exists())
            self.assertTrue((repo_root / ".git_scripts" / "new_branch.sh").is_file())

            exclude_path = Path(
                subprocess.run(
                    ["git", "-C", str(repo_root), "rev-parse", "--path-format=absolute", "--git-path", "info/exclude"],
                    check=True,
                    capture_output=True,
                    text=True,
                ).stdout.strip()
            )
            exclude_text = exclude_path.read_text(encoding="utf-8")
            self.assertIn(".githooks/", exclude_text)
            self.assertIn(".git_scripts/", exclude_text)
            hooks_path = subprocess.run(
                ["git", "-C", str(repo_root), "config", "--local", "--get", "core.hooksPath"],
                check=True,
                capture_output=True,
                text=True,
            ).stdout.strip()
            self.assertEqual(".githooks", hooks_path)

    def test_export_runtime_templates_restores_placeholders(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            workflow_root = temp_root / "workflow"
            shutil.copytree(self.workflow_root / "profiles", workflow_root / "profiles")
            shutil.copytree(self.workflow_root / "templates", workflow_root / "templates")
            shutil.copytree(self.workflow_root / "repos", workflow_root / "repos")
            self.copy_runtime_sources(workflow_root)

            exported = export_runtime_templates(workflow_root=workflow_root, repo_id="AgentWorkflowKit")
            self.assertTrue(exported)

            assert_workspace_template = (
                workflow_root / "templates" / "full_codex_flow" / "files" / ".git_scripts" / "assert_workspace.sh.tmpl"
            ).read_text(encoding="utf-8")
            self.assertIn("{{ expected_workspace_root }}", assert_workspace_template)
            self.assertIn("{{ default_branch }}", assert_workspace_template)
            self.assertNotIn("/Users/pi/PyCharmProject/AgentWorkflowKit", assert_workspace_template)

            pre_push_template = (
                workflow_root / "templates" / "full_codex_flow" / "files" / ".githooks" / "pre-push.tmpl"
            ).read_text(encoding="utf-8")
            self.assertIn("{{ compile_main_path }}", pre_push_template)
            self.assertIn("{{ compile_test_path }}", pre_push_template)
            self.assertNotIn("src/main/python/agent_workflow_kit", pre_push_template)

            register_sync_template = (
                workflow_root / "templates" / "full_codex_flow" / "files" / ".git_scripts" / "public_work_register_sync.py.tmpl"
            ).read_text(encoding="utf-8")
            self.assertIn("{{ python_package_name }}", register_sync_template)
            self.assertNotIn("agent_workflow_kit.tooling.service", register_sync_template)

    def test_check_release_detects_outdated_then_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            temp_root = Path(tmp_dir)
            workflow_root = temp_root / "workflow"
            shutil.copytree(self.workflow_root / "profiles", workflow_root / "profiles")
            shutil.copytree(self.workflow_root / "templates", workflow_root / "templates")
            (workflow_root / "repos").mkdir(parents=True)

            repo_root = temp_root / "TempRepo"
            repo_root.mkdir(parents=True)
            self.write_repo_docs(repo_root)

            repo_config = {
                "repo_id": "TempRepo",
                "profile": "full_codex_flow",
                "expected_workspace_root": str(repo_root),
                "default_branch": "main",
                "python_package_name": "temp_repo",
                "compile_main_path": "src/main/python/temp_repo",
                "compile_test_path": "src/test/python/temp_repo",
                "public_work_register_dir": str(temp_root / "PublicWorkRegister" / "TempRepo"),
            }
            write_json(workflow_root / "repos" / "TempRepo.json", repo_config)

            def publish(version: str) -> str:
                payload, lock_payload = prepare_release_artifacts(
                    workflow_root=workflow_root,
                    profile="full_codex_flow",
                    version=version,
                    repo_ids=["TempRepo"],
                )
                write_release_artifacts(
                    workflow_root=workflow_root,
                    profile="full_codex_flow",
                    version=version,
                    release_payload=payload,
                    lock_payload=lock_payload,
                )
                return str(payload["release_manifest_hash"])

            manifest_hash_v1 = publish("1.0.0")
            rendered_v1 = render_repo_entries(
                workflow_root=workflow_root,
                repo_root=repo_root,
                repo_config=repo_config,
                workflow_version="1.0.0",
                release_hash=manifest_hash_v1,
            )
            apply_rendered_entries(repo_root, rendered_v1)

            current = check_repo_release(repo_root=repo_root, workflow_root=workflow_root, repo_id="TempRepo")
            self.assertEqual("current", current["status"])

            publish("1.0.1")
            outdated = check_repo_release(repo_root=repo_root, workflow_root=workflow_root, repo_id="TempRepo")
            self.assertEqual("outdated", outdated["status"])

            target_script = repo_root / ".git_scripts" / "new_branch.sh"
            target_script.write_text(target_script.read_text(encoding="utf-8") + "\n# drift\n", encoding="utf-8")
            drift = check_repo_release(repo_root=repo_root, workflow_root=workflow_root, repo_id="TempRepo")
            self.assertEqual("drift", drift["status"])


if __name__ == "__main__":
    unittest.main()
